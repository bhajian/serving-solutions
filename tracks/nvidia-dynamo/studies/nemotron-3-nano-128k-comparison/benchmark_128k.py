"""Run the fixed 128K cohort inside the client pod, clearing caches per repetition."""
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

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=['aggregated', 'disaggregated'])
parser.add_argument('--repetitions', type=int, default=3)
args = parser.parse_args()
if args.repetitions < 1:
    parser.error('repetitions must be positive')
logdir = pathlib.Path('study-records')
logdir.mkdir(exist_ok=True)
# One driver per results directory: a second one would flush caches under a live run.
from benchmarks.driver_lock import DriverBusy, acquire, now  # noqa: E402
try:
    LOCK = acquire(logdir)
except DriverBusy as exc:
    sys.exit(str(exc))
for repetition in range(1, args.repetitions + 1):
    mode = args.mode
    label = f'{mode}-{repetition}'
    start = time.time()
    record = {
        'mode': mode, 'repetition': repetition,
        'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sessions': 32, 'concurrency': 4, 'input_tokens': 128000, 'output_budget': 256,
        'cache_protocol': 'flush both workers before each run; allow within-session prefix reuse',
        'client': 'benchmark-client pod on node 0; Kubernetes ClusterIP',
    }
    code = 1
    try:
        with (logdir / f'{label}-cache-clear.log').open('a') as output:
            output.write(f'# cache clear {now()}\n'); output.flush()
            subprocess.run([sys.executable, 'clear_cache.py', mode], stdout=output,
                           stderr=subprocess.STDOUT, check=True, timeout=540, env={**os.environ, 'BENCH_RUN_LABEL': label})
        command = [
            sys.executable, '-u', '-m', 'benchmarks.run',
            '--base-url', f'http://frontend.{NAMESPACE}.svc.cluster.local:8000/v1',
            '--model', 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16',
            '--technology', 'dynamo-' + ('agg' if mode == 'aggregated' else 'disagg') + '-k8s',
            '--deployment', mode + '-deployment.json', '--dataset', 'dataset.jsonl',
            '--sessions', '32', '--max-model-len', '131072', '--min-input-tokens', '128000',
            '--output-tokens', '256', '--concurrency', '4', '--warmup', '1',
            '--cache-state', 'mixed', '--metrics-url', f"http://{NODE_IPS['NODE_A_IP']}:8081/metrics",
            '--metrics-url', f"http://{NODE_IPS['NODE_B_IP']}:8081/metrics", '--results', 'results',
        ]
        record['command'] = command
        (logdir / f'{label}-started.json').write_text(json.dumps(record, indent=2) + '\n')
        with (logdir / f'{label}-benchmark.log').open('w') as output:
            code = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT).returncode
    finally:
        record.update(exit_code=code, elapsed_seconds=time.time() - start,
                      end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        (logdir / f'{label}-completed.json').write_text(json.dumps(record, indent=2) + '\n')
    print(label, 'completed', code, flush=True)
    if code:
        sys.exit(code)
