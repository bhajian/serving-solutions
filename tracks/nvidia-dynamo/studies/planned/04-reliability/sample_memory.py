#!/usr/bin/env python3
"""Sample a role's container anonymous memory every few seconds (from the pod's cgroup).

    python tracks/nvidia-dynamo/studies/planned/04-reliability/sample_memory.py --context "$KUBE_CONTEXT" \
      --namespace nemotron-3-nano --role prefill --out build/experiments/04-reliability/prefill-memory.csv

Reads memory.stat inside each matching pod, so it needs only kubectl exec. Stop with Ctrl-C.
The 8K/128K diagnostics used the same measurement (anon bytes) to record the 104-308 GiB swing.
"""
import argparse
import csv
import subprocess
import time
from pathlib import Path


def pods(a):
    out = subprocess.run(['kubectl', '--context', a.context, '-n', a.namespace, 'get', 'pods', '-l',
                          f'nvidia.com/dynamo-component-type={a.role}', '-o', 'jsonpath={.items[*].metadata.name}'],
                         capture_output=True, text=True, check=True)
    return out.stdout.split()


def anon_gib(a, pod):
    out = subprocess.run(['kubectl', '--context', a.context, '-n', a.namespace, 'exec', pod, '-c', 'main', '--',
                          'sh', '-c', 'grep "^anon " /sys/fs/cgroup/memory.stat'], capture_output=True, text=True)
    return int(out.stdout.split()[1]) / 2**30 if out.returncode == 0 and out.stdout else None


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--context', required=True); p.add_argument('--namespace', required=True)
    p.add_argument('--role', default='prefill'); p.add_argument('--interval', type=float, default=5)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    with open(a.out, 'a', newline='') as f:
        w = csv.writer(f)
        w.writerow(['elapsed_s', 'pod', 'anon_gib'])
        while True:
            for pod in pods(a):
                w.writerow([round(time.time() - start, 1), pod, anon_gib(a, pod)])
            f.flush()
            time.sleep(a.interval)


if __name__ == '__main__':
    main()
