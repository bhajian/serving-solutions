"""Run 8K-input / 128K-output waves inside the client pod, clearing caches per run.

Pilots use --output-tokens below 131072 and --results pilots; measured runs use
the defaults. Each run sends --concurrency requests at once (one closed-loop wave).
"""
import os
import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import time
# Kubernetes namespace of the serving stack. Runs recorded before 2026-10-02 used
# deepseek-v4-pro for both profiles; each profile now has its own namespace.
NAMESPACE = os.environ.get('BENCH_NAMESPACE', 'nemotron-3-nano')
# Node IPs come from the site env (see platform/site.env.example); never hard-code them.
NODE_IPS = {k: os.environ.get(k) or sys.exit(f'Set {k} (see platform/site.env.example)') for k in ('NODE_A_IP', 'NODE_B_IP')}

METRICS = [f'http://{host}:{port}/metrics' for port in (8081, 8082) for host in (NODE_IPS['NODE_A_IP'], NODE_IPS['NODE_B_IP'])]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=['aggregated', 'disaggregated'])
parser.add_argument('--concurrency', type=int, required=True)
parser.add_argument('--output-tokens', type=int, default=131072)
parser.add_argument('--repetitions', type=int, default=3)
parser.add_argument('--processes', type=int, default=16)
parser.add_argument('--label', default='measured')
parser.add_argument('--results', default='results')
args = parser.parse_args()
if min(args.repetitions, args.concurrency, args.output_tokens) < 1:
    parser.error('repetitions, concurrency and output tokens must be positive')
logdir = pathlib.Path('study-records')
logdir.mkdir(exist_ok=True)
# One driver per results directory: a second one would flush caches under a live run.
from benchmarks.driver_lock import DriverBusy, acquire, now  # noqa: E402
try:
    LOCK = acquire(logdir)
except DriverBusy as exc:
    sys.exit(str(exc))
for repetition in range(1, args.repetitions + 1):
    label = f'{args.mode}-c{args.concurrency}-o{args.output_tokens}-{args.label}-{repetition}'
    start = time.time()
    record = {
        'mode': args.mode, 'repetition': repetition, 'label': args.label,
        'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sessions': args.concurrency, 'concurrency': args.concurrency, 'input_tokens': 8000,
        'output_tokens': args.output_tokens, 'ignore_eos': True,
        'cache_protocol': 'flush all workers before each run; prompts are unique per session',
        'client': 'benchmark-client pod on node 0; Kubernetes ClusterIP',
    }
    code = 1
    try:
        with (logdir / f'{label}-cache-clear.log').open('a') as output:
            output.write(f'# cache clear {now()}\n'); output.flush()
            subprocess.run([sys.executable, 'clear_cache.py', args.mode, '4'], stdout=output,
                           stderr=subprocess.STDOUT, check=True, timeout=540, env={**os.environ, 'BENCH_RUN_LABEL': label})
        command = [
            sys.executable, '-u', '-m', 'benchmarks.long_decode',
            '--base-url', f'http://frontend.{NAMESPACE}.svc.cluster.local:8000/v1',
            '--model', 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16',
            '--technology', 'dynamo-' + ('agg' if args.mode == 'aggregated' else 'disagg') + '-k8s',
            '--deployment', args.mode + '-deployment.json', '--dataset', 'dataset.jsonl',
            '--sessions', str(args.concurrency), '--concurrency', str(args.concurrency),
            '--max-model-len', '262144', '--min-input-tokens', '8000',
            '--output-tokens', str(args.output_tokens), '--processes', str(args.processes),
            '--warmup', '1', '--cache-state', 'cold', '--label', args.label, '--results', args.results,
            *(x for url in METRICS for x in ('--metrics-url', url)),
        ]
        record['command'] = command
        (logdir / f'{label}-started.json').write_text(json.dumps(record, indent=2) + '\n')
        with (logdir / f'{label}-benchmark.log').open('w') as output:
            code = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT).returncode
    finally:
        record.update(exit_code=code, elapsed_seconds=time.time() - start,
                      end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        (logdir / f'{label}-completed.json').write_text(json.dumps(record, indent=2) + '\n')
    print(label, 'completed', code, f'{time.time() - start:.0f}s', flush=True)
    if code:
        sys.exit(code)
