#!/usr/bin/env python3
"""Open- or closed-loop load against an OpenAI-compatible endpoint, reporting goodput at SLO.

    python -m benchmarks.loadgen --base-url http://<frontend>:8000/v1 --model <id> \\
      --technology dynamo-disagg-k8s --dataset sessions.jsonl --max-model-len 262144 \\
      --arrival poisson --rps 4 --duration 600 --slo-ttft-ms 2000 --slo-itl-ms 40 \\
      --gpu-count 16 --gpu-hour-usd 0 --results tracks/nvidia-dynamo/studies/pd-sweep

Arrival processes:
  poisson   sessions start at exponential inter-arrival times with mean 1/rps (open loop)
  constant  sessions start every 1/rps seconds (open loop)
  closed    --concurrency sessions in flight; a new one starts when one finishes

Within a session, turns run back to back (multi-turn prefix reuse), separated by
--think-time. Output length is forced per turn (ignore_eos with max_tokens equal to the
turn's max_output_tokens, else --output-tokens), so the OSL distribution is what the
dataset says.

Primary metric: goodput, the rate of requests that individually meet BOTH targets: TTFT
<= --slo-ttft-ms, and p99 of their own inter-token intervals <= --slo-itl-ms. The summary
also reports SLO attainment (fraction of requests meeting both), whether the run as a
whole meets p99 TTFT and p99 ITL, cost per million output tokens, and cost per million
output tokens at SLO. Output layout matches benchmarks.run and benchmarks.long_decode
(summary.csv/json, requests.csv, metadata.json, metrics-*.prom), plus an AIPerf /
genai-perf compatible profile_export.json (see benchmarks/README.md for definitions).
"""
import argparse
import asyncio
import hashlib
import json
import math
import multiprocessing
import os
import platform
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

from benchmarks.long_decode import server_histograms, stream_request
from benchmarks.metrics import distribution
from benchmarks.run import load_sessions, snapshot_metrics, write_csv


# --------------------------------------------------------------------------- arrivals

def arrival_times(kind, rps, count, seed):
    """Session start offsets in seconds. Deterministic for a given seed."""
    if kind == 'closed':
        return [0.0] * count
    if rps <= 0:
        raise ValueError('open-loop arrivals need --rps > 0')
    if kind == 'constant':
        return [i / rps for i in range(count)]
    if kind == 'poisson':
        rng = random.Random(f'{seed}:arrivals')
        t, out = 0.0, []
        for _ in range(count):
            out.append(t)
            t += rng.expovariate(rps)
        return out
    raise ValueError(f'unknown arrival process {kind!r}')


# --------------------------------------------------------------------------- goodput and cost

def request_meets_slo(row, ttft_ms, itl_ms):
    if not row.get('measurement_valid'):
        return False
    ttft_ok = row.get('ttft_ms') is not None and row['ttft_ms'] <= ttft_ms
    itl = row.get('itl_ms_p99')
    # A single-token response has no inter-token interval: only TTFT applies.
    itl_ok = itl is None and row.get('completion_tokens') == 1 or (itl is not None and itl <= itl_ms)
    return bool(ttft_ok and itl_ok)


def goodput(rows, wall_s, ttft_ms, itl_ms, pooled_itl):
    valid = [r for r in rows if r.get('measurement_valid')]
    ok = [r for r in valid if request_meets_slo(r, ttft_ms, itl_ms)]
    ttfts = [r['ttft_ms'] for r in valid if r.get('ttft_ms') is not None]
    p99_ttft = float(np.percentile(ttfts, 99)) if ttfts else None
    p99_itl = float(np.percentile(pooled_itl, 99)) if len(pooled_itl) else None
    return {
        'slo_ttft_ms': ttft_ms, 'slo_itl_ms': itl_ms,
        'goodput_rps': len(ok) / wall_s if wall_s > 0 else None,
        'goodput_output_tps': sum(r['completion_tokens'] for r in ok) / wall_s if wall_s > 0 else None,
        'slo_attainment': len(ok) / len(valid) if valid else None,
        'run_p99_ttft_ms': p99_ttft, 'run_p99_itl_ms': p99_itl,
        'run_meets_slo': bool(p99_ttft is not None and p99_ttft <= ttft_ms and
                              (p99_itl is None or p99_itl <= itl_ms)),
        'slo_requests': len(ok), 'slo_output_tokens': sum(r['completion_tokens'] for r in ok),
    }


def cost(gpu_count, gpu_hour_usd, wall_s, output_tokens, slo_output_tokens):
    """Cost per million output tokens, overall and counting only requests that met the SLO."""
    if not gpu_hour_usd:
        return {'gpu_hour_usd': gpu_hour_usd, 'usd_per_m_output_tokens': None, 'usd_per_m_output_tokens_at_slo': None}
    usd = gpu_count * gpu_hour_usd * wall_s / 3600
    per_m = lambda tokens: usd / (tokens / 1e6) if tokens else None
    return {'gpu_hour_usd': gpu_hour_usd, 'run_cost_usd': usd,
            'usd_per_m_output_tokens': per_m(output_tokens), 'usd_per_m_output_tokens_at_slo': per_m(slo_output_tokens)}


# --------------------------------------------------------------------------- AIPerf / genai-perf export

def aiperf_export(rows, wall_s, pooled_itl):
    """profile_export.json with genai-perf/AIPerf metric names and units.

    Definition differences (documented in benchmarks/README.md): genai-perf's
    inter_token_latency is a per-request average, (e2e - ttft) / (osl - 1), which is our
    TPOT. Our token-gap distribution is exported separately as inter_token_gap.
    """
    valid = [r for r in rows if r.get('measurement_valid')]
    def stats(values, unit):
        v = np.asarray([x for x in values if x is not None], dtype=float)
        if not len(v):
            return {'unit': unit}
        return {'unit': unit, 'avg': float(v.mean()), 'min': float(v.min()), 'max': float(v.max()),
                'std': float(v.std()), **{f'p{p}': float(np.percentile(v, p)) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)}}
    out_tokens = sum(r['completion_tokens'] for r in valid)
    return {
        'request_throughput': {'unit': 'requests/sec', 'avg': len(valid) / wall_s if wall_s else None},
        'output_token_throughput': {'unit': 'tokens/sec', 'avg': out_tokens / wall_s if wall_s else None},
        'request_latency': stats([r['e2e_ms'] for r in valid], 'ms'),
        'time_to_first_token': stats([r['ttft_ms'] for r in valid], 'ms'),
        'inter_token_latency': stats([r['tpot_ms'] for r in valid], 'ms'),
        'inter_token_gap': stats(pooled_itl, 'ms'),
        'output_sequence_length': stats([r['completion_tokens'] for r in valid], 'tokens'),
        'input_sequence_length': stats([r['prompt_tokens'] for r in valid], 'tokens'),
        'request_count': {'unit': 'requests', 'avg': len(valid)},
    }


# --------------------------------------------------------------------------- client processes

async def run_sessions(jobs, a, extra, run_start_at, client, rows, intervals_out):
    """Run one process's share of sessions. jobs: [(session_index, start_offset_s, sample)]."""
    sem = asyncio.Semaphore(a.concurrency) if a.concurrency else None

    async def session(index, offset, sample):
        await asyncio.sleep(max(0.0, run_start_at + offset - time.perf_counter()))
        if sem:
            await sem.acquire()
        try:
            started = time.perf_counter() - run_start_at
            for turn_index, turn in enumerate(sample['turns']):
                budget = turn.get('max_output_tokens', a.output_tokens)
                body = {'model': a.model, 'messages': turn['messages'], 'max_tokens': budget,
                        'temperature': a.temperature, 'stream': True, 'ignore_eos': True,
                        'stream_options': {'include_usage': True}, **extra}
                if turn.get('tools'):
                    body['tools'] = turn['tools']
                row, intervals = await stream_request(client, a.base_url, body, a.timeout, run_start_at)
                n, prompt = row['completion_tokens'], row['prompt_tokens']
                issues = []
                if not isinstance(n, int) or not isinstance(prompt, int):
                    issues.append('missing_or_invalid_server_usage')
                elif n != budget:
                    issues.append('completion_tokens_differ_from_forced_length')
                elif prompt + budget > a.max_model_len:
                    issues.append('input_plus_reserved_output_exceeds_context')
                row['measurement_valid'] = row['success'] and not issues
                row['measurement_issue'] = ';'.join(issues)
                row.update(session_id=sample['id'], session_index=index, turn=turn_index,
                           scheduled_start_s=offset, start_lag_ms=(started - offset) * 1000 if turn_index == 0 else 0,
                           planned_input_tokens=turn.get('input_tokens'), requested_output_tokens=budget,
                           request_sha256=hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest())
                row['slo_met'] = request_meets_slo(row, a.slo_ttft_ms, a.slo_itl_ms)
                rows.append(row)
                intervals_out.append(np.frombuffer(intervals, dtype=np.float32).copy() if len(intervals) else
                                     np.zeros(0, dtype=np.float32))
                if a.think_time and turn_index + 1 < len(sample['turns']):
                    await asyncio.sleep(a.think_time)
        finally:
            if sem:
                sem.release()

    await asyncio.gather(*(session(i, o, s) for i, o, s in jobs))


def client_process(index, jobs, a, extra, out, run_start_at):
    async def main():
        rows, intervals = [], []
        limits = httpx.Limits(max_connections=max(64, len(jobs) + 4), max_keepalive_connections=64)
        async with httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(a.timeout, connect=30)) as client:
            await run_sessions(jobs, a, extra, run_start_at, client, rows, intervals)
        with (out / f'rows-{index:02d}.jsonl').open('w') as f:
            for r in rows:
                f.write(json.dumps(r) + '\n')
        np.save(out / f'itl-{index:02d}.npy', np.concatenate(intervals) if intervals else np.zeros(0, dtype=np.float32))
    asyncio.run(main())


# --------------------------------------------------------------------------- run

def summarize(rows, wall, pooled, a, deployment):
    valid = [r for r in rows if r['measurement_valid']]
    out_tokens = sum(r['completion_tokens'] for r in valid)
    s = {'requests': len(rows), 'successful_requests': sum(r['success'] for r in rows),
         'failed_requests': sum(not r['success'] for r in rows),
         'valid_measurements': len(valid), 'invalid_measurements': sum(r['success'] and not r['measurement_valid'] for r in rows),
         'duration_s': wall, 'total_output_tokens': out_tokens,
         'total_input_tokens': sum(r['prompt_tokens'] for r in valid),
         'request_throughput_rps': len(valid) / wall if wall > 0 else None,
         'output_throughput_tps': out_tokens / wall if wall > 0 else None,
         'offered_rps': a.rps if a.arrival != 'closed' else None, 'arrival': a.arrival}
    for key in ('ttft_ms', 'tpot_ms', 'e2e_ms', 'start_lag_ms', 'prompt_tokens', 'completion_tokens'):
        s.update(distribution(key, [r.get(key) for r in valid]))
    if len(pooled):
        s.update({'itl_ms_mean': float(pooled.mean()), 'itl_ms_max': float(pooled.max()),
                  **{f'itl_ms_p{p}': float(np.percentile(pooled, p)) for p in (50, 90, 95, 99)},
                  'itl_ms_p99_9': float(np.percentile(pooled, 99.9))})
    s.update(goodput(rows, wall, a.slo_ttft_ms, a.slo_itl_ms, pooled))
    s.update(cost(a.gpu_count, a.gpu_hour_usd, wall, out_tokens, s['slo_output_tokens']))
    topology = json.loads(a.topology) if a.topology else {}
    s.update({f'topo_{k}': v for k, v in topology.items()})
    s.update(technology=a.technology, model=a.model, gpu_count=a.gpu_count, label=a.label,
             image=deployment.get('image', 'unrecorded'), topology=deployment.get('topology', topology.get('mode', 'unrecorded')))
    return s


def run(a):
    sessions = load_sessions(a.dataset, a.sessions, a.max_model_len, a.output_tokens)
    deployment = json.loads(Path(a.deployment).read_text()) if a.deployment else {}
    extra = deployment.get('model', {}).get('request_body', {}) | json.loads(a.extra_body)
    reserved = {'messages', 'model', 'stream', 'stream_options', 'max_tokens', 'ignore_eos'}
    if extra.keys() & reserved:
        raise ValueError(f'extra-body may not override {sorted(extra.keys() & reserved)}')
    starts = arrival_times(a.arrival, a.rps, len(sessions), a.seed)
    if a.duration:
        keep = [i for i, t in enumerate(starts) if t < a.duration]
        sessions, starts = [sessions[i] for i in keep], [starts[i] for i in keep]
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    out = Path(a.results) / run_id; out.mkdir(parents=True, exist_ok=False)
    metadata = {**vars(a), 'run_id': run_id, 'runner': 'benchmarks.loadgen', 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                'dataset_sha256': hashlib.sha256(Path(a.dataset).read_bytes()).hexdigest(), 'deployment': deployment,
                'resolved_extra_body': extra, 'sessions_scheduled': len(sessions), 'python': sys.version,
                'platform': platform.platform(), 'cpu_count': os.cpu_count()}
    (out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')

    async def snap(phase):
        async with httpx.AsyncClient(timeout=30) as client:
            await snapshot_metrics(client, a.metrics_url, out, phase)

    asyncio.run(snap('before'))
    jobs = [[] for _ in range(a.processes)]
    for i, (sample, t) in enumerate(zip(sessions, starts)):
        jobs[i % a.processes].append((i, t, sample))
    run_start_at = time.perf_counter() + 2
    ctx = multiprocessing.get_context('fork')
    procs = [ctx.Process(target=client_process, args=(i, jobs[i], a, extra, out, run_start_at))
             for i in range(a.processes) if jobs[i]]
    for p in procs: p.start()
    for p in procs: p.join()
    wall = time.perf_counter() - run_start_at
    asyncio.run(snap('after'))
    if any(p.exitcode for p in procs):
        raise RuntimeError(f'client process failed: {[p.exitcode for p in procs]}')
    rows = sorted((json.loads(l) for f in sorted(out.glob('rows-*.jsonl')) for l in f.read_text().splitlines() if l),
                  key=lambda r: (r['session_index'], r['turn']))
    pooled = np.concatenate([np.load(f) for f in sorted(out.glob('itl-*.npy'))] or [np.zeros(0, dtype=np.float32)])
    write_csv(out / 'requests.csv', rows)
    s = summarize(rows, wall, pooled, a, deployment)
    s.update(server_histograms(out, len(a.metrics_url)), run_id=run_id, dataset_sha256=metadata['dataset_sha256'])
    write_csv(out / 'summary.csv', [s])
    (out / 'summary.json').write_text(json.dumps(s, indent=2) + '\n')
    (out / 'profile_export.json').write_text(json.dumps(aiperf_export(rows, wall, pooled), indent=2) + '\n')
    print(json.dumps({k: s.get(k) for k in ('valid_measurements', 'requests', 'goodput_rps', 'slo_attainment',
                                            'run_meets_slo', 'output_throughput_tps', 'ttft_ms_p99', 'itl_ms_p99',
                                            'usd_per_m_output_tokens_at_slo')}, indent=2))
    print('Results:', out)
    return 0 if s['failed_requests'] == 0 and s['invalid_measurements'] == 0 else 1


def parser():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--base-url', required=True); p.add_argument('--model', required=True)
    p.add_argument('--technology', required=True, choices=['dynamo-agg-k8s', 'dynamo-disagg-k8s', 'llmd-k8s'])
    p.add_argument('--dataset', required=True); p.add_argument('--deployment')
    p.add_argument('--max-model-len', type=int, required=True)
    p.add_argument('--output-tokens', type=int, default=512, help='Forced length for turns without max_output_tokens')
    p.add_argument('--arrival', choices=['poisson', 'constant', 'closed'], default='poisson')
    p.add_argument('--rps', type=float, default=0, help='Session arrival rate for open-loop runs')
    p.add_argument('--concurrency', type=int, default=0, help='Closed loop: sessions in flight. Open loop: optional cap; 0 = none')
    p.add_argument('--duration', type=float, default=0, help='Open loop: only schedule sessions starting within this many seconds')
    p.add_argument('--sessions', type=int, default=0)
    p.add_argument('--think-time', type=float, default=0)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--slo-ttft-ms', type=float, required=True); p.add_argument('--slo-itl-ms', type=float, required=True)
    p.add_argument('--gpu-count', type=int, required=True)
    p.add_argument('--gpu-hour-usd', type=float, default=0, help='Price per GPU-hour; 0 leaves cost columns blank')
    p.add_argument('--topology', default='', help='JSON with sweep coordinates, e.g. {"mode":"disagg","prefill":1,"decode":3,"tp_prefill":4,"tp_decode":4}')
    p.add_argument('--processes', type=int, default=8)
    p.add_argument('--timeout', type=float, default=3600)
    p.add_argument('--temperature', type=float, default=0)
    p.add_argument('--extra-body', default='{}')
    p.add_argument('--metrics-url', action='append', default=[])
    p.add_argument('--label', default='')
    p.add_argument('--results', default='results')
    return p


def main():
    p = parser(); a = p.parse_args()
    if a.arrival == 'closed' and a.concurrency < 1:
        p.error('closed-loop runs need --concurrency >= 1')
    if a.arrival != 'closed' and a.rps <= 0:
        p.error('open-loop runs need --rps > 0')
    if min(a.processes, a.gpu_count) < 1 or a.slo_ttft_ms <= 0 or a.slo_itl_ms <= 0:
        p.error('processes, gpu count and SLO targets must be positive')
    try:
        raise SystemExit(run(a))
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        p.exit(2, f'{exc}\n')


if __name__ == '__main__':
    main()
