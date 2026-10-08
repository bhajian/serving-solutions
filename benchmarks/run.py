#!/usr/bin/env python3
"""Benchmark an OpenAI-compatible streaming endpoint with recorded sessions."""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import uuid

import httpx

from benchmarks.metrics import request_metrics, summarize


async def sse_events(response):
    """Handle comments, multi-line data, CRLF and arbitrary transport splitting."""
    data = []
    async for line in response.aiter_lines():
        if not line:
            if data:
                yield '\n'.join(data)
                data = []
        elif line.startswith('data:'):
            data.append(line[5:].removeprefix(' '))
    if data:
        yield '\n'.join(data)


async def request(client, url, body, timeout, min_input, max_context):
    start = time.perf_counter()
    events, usage, chunks = [], {}, []
    first_content = None
    finish_reason, error, done, status = None, '', False, None
    try:
        async with asyncio.timeout(timeout):
            async with client.stream('POST', url.rstrip('/') + '/chat/completions', json=body) as response:
                status = response.status_code
                if status != 200:
                    await response.aread()
                    raise RuntimeError(f'HTTP {status}: {response.text[:1000]}')
                async for data in sse_events(response):
                    elapsed = time.perf_counter() - start
                    if data.strip() == '[DONE]':
                        done = True
                        break
                    obj = json.loads(data)
                    if obj.get('error'):
                        raise RuntimeError(str(obj['error']))
                    if obj.get('usage'):
                        usage = obj['usage']
                    choices = obj.get('choices') or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get('delta') or {}
                    ids = choice.get('token_ids', delta.get('token_ids'))
                    text = delta.get('content') or ''
                    reasoning = delta.get('reasoning_content') or delta.get('reasoning') or ''
                    calls = delta.get('tool_calls') or []
                    has_tool_payload = any(t.get('function', {}).get('arguments') or
                                           t.get('function', {}).get('name') for t in calls)
                    if text and first_content is None:
                        first_content = elapsed * 1000
                    if text or reasoning or has_tool_payload or ids:
                        events.append({'time_s': elapsed, 'token_count': len(ids) if ids is not None else None})
                    if delta or ids:
                        chunks.append({'time_s': elapsed, 'delta': delta, 'token_ids': ids})
                    if choice.get('finish_reason'):
                        finish_reason = choice['finish_reason']
                        if finish_reason == 'error':
                            raise RuntimeError('Server sent finish_reason=error')
        if not done:
            raise RuntimeError('Stream ended without [DONE]')
        if finish_reason is None:
            raise RuntimeError('Stream ended without finish_reason')
        if not events:
            raise RuntimeError('Stream returned no generated output')
    except (httpx.HTTPError, RuntimeError, ValueError, TimeoutError) as exc:
        error = f'{type(exc).__name__}: {exc}'
    duration = time.perf_counter() - start
    n = usage.get('completion_tokens')
    prompt = usage.get('prompt_tokens')
    issues = []
    if not isinstance(prompt, int) or prompt < 0 or not isinstance(n, int) or n < 1:
        issues.append('missing_or_invalid_server_usage')
        n = n if isinstance(n, int) and n >= 0 else None
        prompt = prompt if isinstance(prompt, int) and prompt >= 0 else None
    if prompt is not None:
        if prompt < min_input:
            issues.append('input_below_requested_minimum')
        if prompt + body['max_tokens'] > max_context:
            issues.append('input_plus_reserved_output_exceeds_context')
    return {'success': not error, 'error': error, 'http_status': status,
            'measurement_valid': not error and not issues, 'measurement_issue': ';'.join(issues),
            'prompt_tokens': prompt, 'completion_tokens': n,
            'cached_tokens': (usage.get('prompt_tokens_details') or {}).get('cached_tokens'),
            'finish_reason': finish_reason, 'first_content_ms': first_content,
            **request_metrics(events, duration, n), 'events': events, 'chunks': chunks,
            'usage': usage}


def write_csv(path, rows):
    if not rows:
        return
    fields = list(rows[0])
    with Path(path).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


async def snapshot_metrics(client, urls, out, phase):
    for i, url in enumerate(urls):
        try:
            r = await client.get(url, timeout=30); r.raise_for_status()
            (out / f'metrics-{phase}-{i}.prom').write_text(r.text)
        except httpx.HTTPError as exc:
            (out / f'metrics-{phase}-{i}.error.txt').write_text(str(exc))


def load_sessions(path, limit, max_context, output_tokens):
    sessions = []
    with Path(path).open() as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get('turns') or row.get('workload') not in ('agentic', 'chatbot'):
                raise ValueError('Each JSONL row needs workload=agentic|chatbot and a nonempty turns list')
            for turn in row['turns']:
                if not turn.get('messages'):
                    raise ValueError('Each turn needs messages')
                if turn.get('input_tokens', 0) + output_tokens > max_context:
                    raise ValueError(f'{row["id"]}: recorded input plus output reservation exceeds context')
            sessions.append(row)
            if limit and len(sessions) >= limit:
                break
    if not sessions:
        raise ValueError('Empty dataset')
    if len({r['id'] for r in sessions}) != len(sessions):
        raise ValueError('Session IDs must be unique')
    if len({r['workload'] for r in sessions}) != 1:
        raise ValueError('Run chatbot and agentic datasets separately for comparable summaries')
    return sessions


async def run(a):
    sessions = load_sessions(a.dataset, a.sessions, a.max_model_len, a.output_tokens)
    deployment = json.loads(Path(a.deployment).read_text()) if a.deployment else {}
    declared_backend = deployment.get('backend', 'vllm')
    if a.backend and deployment and a.backend != declared_backend:
        raise ValueError('--backend must match deployment.json')
    a.backend = a.backend or declared_backend
    if a.token_ids and a.backend == 'sglang':
        raise ValueError('--token-ids uses a vLLM extension; omit it for SGLang. Token-resolved ITL may be unavailable.')
    extra = json.loads(a.extra_body)
    reserved = {'messages', 'tools', 'model', 'stream', 'stream_options', 'max_tokens', 'n'}
    if extra.keys() & reserved:
        raise ValueError('extra-body may not override structural fields: ' + str(extra.keys() & reserved))
    if deployment:
        if deployment.get('technology', a.technology) != a.technology:
            raise ValueError('--technology must match deployment.json')
        if deployment['model']['model_id'] != a.model or deployment['max_model_len'] != a.max_model_len:
            raise ValueError('--model and --max-model-len must match deployment.json')
        extra = deployment['model'].get('request_body', {}) | extra
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    out = Path(a.results) / run_id; out.mkdir(parents=True, exist_ok=False)
    metadata = {k: v for k, v in vars(a).items() if k != 'api_key_env'}
    metadata.update(run_id=run_id, timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    dataset_sha256=hashlib.sha256(Path(a.dataset).read_bytes()).hexdigest(),
                    deployment=deployment, python=sys.version, platform=platform.platform(),
                    resolved_extra_body=extra, load_mode='closed-loop' if not a.session_rate else 'paced-sessions',
                    workload=sessions[0]['workload'], session_count=len(sessions))
    (out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    # Preserve workload construction metadata without copying huge prompt files.
    dataset_meta = Path(a.dataset + '.meta.json')
    if dataset_meta.exists():
        (out / 'dataset.meta.json').write_text(dataset_meta.read_text())
    token = os.environ.get(a.api_key_env)
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    rows = []
    limits = httpx.Limits(max_connections=max(a.concurrency + 4, 16), max_keepalive_connections=a.concurrency)
    async with httpx.AsyncClient(headers=headers, limits=limits, timeout=httpx.Timeout(a.timeout, connect=30)) as client:
        models = await client.get(a.base_url.rstrip('/') + '/models')
        models.raise_for_status()
        if a.model not in [x['id'] for x in models.json().get('data', [])]:
            raise ValueError('Requested model is absent from /v1/models')
        # Short, disjoint prompt avoids warming the measured long prefixes.
        for i in range(a.warmup):
            body = {'model': a.model, 'messages': [{'role': 'user', 'content': f'Warmup {run_id}-{i}: say hello.'}],
                    'max_tokens': 16, 'temperature': 0, 'stream': True,
                    'stream_options': {'include_usage': True}, **extra}
            result = await request(client, a.base_url, body, a.timeout, 0, a.max_model_len)
            if not result['success']:
                raise RuntimeError('Warmup failed: ' + result['error'])
        await snapshot_metrics(client, a.metrics_url, out, 'before')
        sem = asyncio.Semaphore(a.concurrency)
        start = time.perf_counter()
        raw = (out / 'requests.jsonl').open('w')

        async def session(index, sample):
            scheduled = start + index / a.session_rate if a.session_rate else start
            if a.session_rate:
                await asyncio.sleep(max(0, scheduled - time.perf_counter()))
            async with sem:
                queue_ms = (time.perf_counter() - scheduled) * 1000
                for turn_index, turn in enumerate(sample['turns']):
                    body = {'model': a.model, 'messages': turn['messages'], 'max_tokens': a.output_tokens,
                            'temperature': a.temperature, 'stream': True,
                            'stream_options': {'include_usage': True}, **extra}
                    if turn.get('tools'):
                        body['tools'] = turn['tools']
                    if a.token_ids:
                        body['return_token_ids'] = True
                    r = await request(client, a.base_url, body, a.timeout, a.min_input_tokens, a.max_model_len)
                    r.update(run_id=run_id, backend=a.backend, technology=a.technology,
                             session_id=sample['id'], turn=turn_index,
                             workload=sample['workload'], client_queue_ms=queue_ms if turn_index == 0 else 0,
                             planned_input_tokens=turn.get('input_tokens'),
                             request_sha256=hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest())
                    rows.append(r)
                    raw.write(json.dumps(r) + '\n'); raw.flush()
                    print(f'{sample["id"]}/{turn_index}: success={r["success"]} valid={r["measurement_valid"]} '
                          f'TTFT={r["ttft_ms"]}ms output={r["completion_tokens"]}', flush=True)
                    # Replay snapshots are independent of sampled outputs. Keep
                    # all turns even after an error, so failures stay measurable.
                    if a.think_time and turn_index + 1 < len(sample['turns']):
                        await asyncio.sleep(a.think_time)
        try:
            await asyncio.gather(*(session(i, s) for i, s in enumerate(sessions)))
        finally:
            raw.close()
        wall = time.perf_counter() - start
        await snapshot_metrics(client, a.metrics_url, out, 'after')
    scalar = [{k: v for k, v in row.items() if not isinstance(v, (list, dict))} for row in rows]
    write_csv(out / 'requests.csv', scalar)
    summary = summarize(rows, wall)
    summary.update(run_id=run_id, timestamp_utc=metadata['timestamp_utc'], technology=a.technology, backend=a.backend,
                   model=a.model, workload=metadata['workload'], concurrency=a.concurrency,
                   session_rate=a.session_rate, think_time_s=a.think_time, sessions=len(sessions),
                   max_model_len=a.max_model_len, requested_output_tokens=a.output_tokens,
                   min_input_tokens=a.min_input_tokens, dataset_sha256=metadata['dataset_sha256'],
                   cache_state=a.cache_state, temperature=a.temperature,
                   extra_body_json=json.dumps(extra, sort_keys=True), image=deployment.get('image', 'unrecorded'),
                   model_revision=deployment.get('model', {}).get('revision', 'unrecorded'),
                   gpu_count=deployment.get('gpu_count', 16), deployment_sha256=hashlib.sha256(json.dumps(deployment, sort_keys=True).encode()).hexdigest())
    write_csv(out / 'summary.csv', [summary])
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('Results:', out)
    # Invalid long-context samples must never look like a successful experiment.
    return 0 if summary['failed_requests'] == 0 and summary['invalid_measurements'] == 0 else 1


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', required=True, help='API URL including /v1')
    p.add_argument('--model', required=True)
    p.add_argument('--technology', required=True, choices=[
        'dynamo-agg-compose', 'dynamo-agg-k8s',        # tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated
        'dynamo-disagg-compose', 'dynamo-disagg-k8s',  # B300 reference tracks 02, 03
        'llmd-k8s',                                    # tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b
        'dynamo-compose', 'dynamo-k8s'],               # legacy labels (= disaggregated)
        help='Must match the "technology" field of --deployment when both are given')
    p.add_argument('--backend', choices=['vllm', 'sglang'],
                   help='Inferred from deployment.json; defaults to vllm without a deployment record')
    p.add_argument('--dataset', required=True); p.add_argument('--deployment')
    p.add_argument('--max-model-len', type=int, required=True)
    p.add_argument('--min-input-tokens', type=int, default=0)
    p.add_argument('--output-tokens', type=int, default=512)
    p.add_argument('--concurrency', type=int, default=1, help='Concurrent sessions; one in-flight turn per session')
    p.add_argument('--session-rate', type=float, default=0, help='Sessions/s; 0 means closed-loop saturation')
    p.add_argument('--sessions', type=int, default=0, help='0 means all JSONL sessions')
    p.add_argument('--think-time', type=float, default=0)
    p.add_argument('--warmup', type=int, default=1)
    p.add_argument('--timeout', type=float, default=3600)
    p.add_argument('--temperature', type=float, default=0)
    p.add_argument('--extra-body', default='{}')
    p.add_argument('--token-ids', action='store_true', help='Request return_token_ids; endpoint support varies')
    p.add_argument('--cache-state', choices=['cold', 'warm', 'mixed', 'uncontrolled'], default='uncontrolled')
    p.add_argument('--api-key-env', default='BENCHMARK_API_KEY')
    p.add_argument('--metrics-url', action='append', default=[], help='Repeat for prefill/decode Prometheus URLs')
    p.add_argument('--results', default='results')
    return p


def main():
    p = parser(); a = p.parse_args()
    if min(a.concurrency, a.output_tokens, a.max_model_len) < 1 or a.timeout <= 0:
        p.error('Concurrency, tokens, context and timeout must be positive')
    if min(a.min_input_tokens, a.sessions, a.session_rate, a.think_time, a.warmup) < 0:
        p.error('Counts/rates cannot be negative')
    if a.min_input_tokens + a.output_tokens > a.max_model_len:
        p.error('Minimum input plus output reservation exceeds context')
    try:
        raise SystemExit(asyncio.run(run(a)))
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        p.exit(2, f'{exc}\n')


if __name__ == '__main__':
    main()
