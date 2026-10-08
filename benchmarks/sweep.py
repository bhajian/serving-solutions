#!/usr/bin/env python3
"""Sweep RPS x P:D ratio x TP per role, then tabulate goodput at SLO.

    python -m benchmarks.sweep plan  tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/sweep.yaml   # print the run matrix
    python -m benchmarks.sweep run   tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/sweep.yaml   # needs cluster access
    python -m benchmarks.sweep table tracks/nvidia-dynamo/studies/pd-ratio-h200                     # summary table (offline)

Spec (YAML):
  study, results, dataset, gpu_count, gpu_hour_usd, slo: {ttft_ms, itl_ms}
  loadgen: extra benchmarks.loadgen arguments (arrival, duration, processes, max_model_len, ...)
  rps: [..]                           # offered session rates
  configs: [{name, overlay, technology, base_url, topology: {...}, wait: <kubectl wait target>}]

Each run lands in <results>/<run_id>/ exactly like benchmarks.loadgen, so the comparison
notebooks and benchmarks.collect read sweep results unchanged.
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import yaml

TABLE_FIELDS = ['config', 'topo_mode', 'topo_prefill', 'topo_decode', 'topo_workers', 'topo_tp_prefill', 'topo_tp_decode',
                'topo_tp', 'offered_rps', 'goodput_rps', 'slo_attainment', 'run_meets_slo', 'output_throughput_tps',
                'goodput_output_tps', 'ttft_ms_p50', 'run_p99_ttft_ms', 'itl_ms_p50', 'run_p99_itl_ms', 'itl_ms_p99_9',
                'tpot_ms_p50', 'usd_per_m_output_tokens', 'usd_per_m_output_tokens_at_slo', 'valid_measurements',
                'requests', 'run_id']


def load_spec(path):
    spec = yaml.safe_load(Path(path).read_text())
    for key in ('study', 'results', 'dataset', 'gpu_count', 'slo', 'rps', 'configs'):
        if key not in spec:
            raise ValueError(f'sweep spec missing {key!r}')
    names = [c['name'] for c in spec['configs']]
    if len(set(names)) != len(names):
        raise ValueError('config names must be unique')
    return spec


def plan(spec):
    """Every (config, rps) run, in execution order: all RPS levels per applied config."""
    return [{'config': c['name'], 'rps': r, 'overlay': c.get('overlay'), 'technology': c['technology'],
             'base_url': c['base_url'], 'topology': c.get('topology', {})} for c in spec['configs'] for r in spec['rps']]


def loadgen_args(spec, step):
    lg = dict(spec.get('loadgen', {}))
    args = [sys.executable, '-m', 'benchmarks.loadgen', '--base-url', step['base_url'], '--model', spec['model'],
            '--technology', step['technology'], '--dataset', spec['dataset'], '--rps', str(step['rps']),
            '--slo-ttft-ms', str(spec['slo']['ttft_ms']), '--slo-itl-ms', str(spec['slo']['itl_ms']),
            '--gpu-count', str(spec['gpu_count']), '--gpu-hour-usd', str(spec.get('gpu_hour_usd') or 0),
            '--topology', json.dumps({**step['topology'], 'config': step['config']}),
            '--label', f'{spec["study"]}:{step["config"]}', '--results', spec['results']]
    for key, value in lg.items():
        flag = '--' + key.replace('_', '-')
        for v in (value if isinstance(value, list) else [value]):
            args += [flag, str(v)]
    return args


def metrics_urls(context, namespace, selector, port=9090):
    """Worker metric endpoints for snapshots: pod IPs of the graph's worker pods."""
    out = subprocess.run(['kubectl', '--context', context, '-n', namespace, 'get', 'pods', '-l', selector,
                          '-o', 'jsonpath={.items[*].status.podIP}'], capture_output=True, text=True, check=True)
    return [f'http://{ip}:{port}/metrics' for ip in out.stdout.split()]


def in_pod(cmd, context, exec_pod):
    """Run a loadgen command inside the benchmark client pod (namespace/pod)."""
    namespace, pod = exec_pod.split('/')
    return ['kubectl', '--context', context, '-n', namespace, 'exec', pod, '-c', 'client', '--', 'python3', *cmd[1:]]


def run(spec, context, dry_run=False, exec_pod=None):
    from benchmarks.driver_lock import acquire
    lock = acquire(Path(spec.get('local_records', spec['results'])) / 'study-records')  # one sweep at a time
    applied, discovered = None, []
    for step in plan(spec):
        cfg = next(c for c in spec['configs'] if c['name'] == step['config'])
        if cfg.get('overlay') and applied != cfg['name']:
            cmds = [['kubectl', '--context', context, 'apply', '-k', cfg['overlay']]]
            if cfg.get('wait'):
                cmds.append(['kubectl', '--context', context, 'wait', '--for=condition=Ready', cfg['wait'], '--timeout=60m'])
            for cmd in cmds:
                print('+', ' '.join(cmd), flush=True)
                if not dry_run:
                    subprocess.run(cmd, check=True)
            applied = cfg['name']
            if spec.get('metrics_selector') and not dry_run:
                discovered = metrics_urls(context, spec['namespace'], spec['metrics_selector'])
        cmd = loadgen_args(spec, step) + [x for url in discovered for x in ('--metrics-url', url)]
        if exec_pod:
            cmd = in_pod(cmd, context, exec_pod)
        print('+', ' '.join(cmd), flush=True)
        if not dry_run:
            subprocess.run(cmd, check=True)
    lock.close()


def table(results):
    rows = []
    for path in sorted(Path(results).glob('*/summary.json')):
        s = json.loads(path.read_text())
        if 'goodput_rps' not in s:
            continue
        s['config'] = s.get('topo_config', s.get('label', ''))
        rows.append({k: s.get(k) for k in TABLE_FIELDS})
    rows.sort(key=lambda r: (str(r['config']), r['offered_rps'] or 0))
    best = {}
    for r in rows:
        if r['run_meets_slo'] and (r['config'] not in best or (r['goodput_rps'] or 0) > (best[r['config']]['goodput_rps'] or 0)):
            best[r['config']] = r
    for r in rows:
        r['best_at_slo'] = best.get(r['config']) is r
    out = Path(results) / 'sweep-table.csv'
    with out.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=TABLE_FIELDS + ['best_at_slo']); w.writeheader(); w.writerows(rows)
    return out, rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    for name in ('plan', 'run'):
        s = sub.add_parser(name); s.add_argument('spec')
        if name == 'run':
            s.add_argument('--context', required=True, help='kube context'); s.add_argument('--dry-run', action='store_true')
            s.add_argument('--exec-pod', help='namespace/pod of the benchmark client; loadgen runs there')
    t = sub.add_parser('table'); t.add_argument('results')
    a = p.parse_args(argv)
    if a.cmd == 'plan':
        spec = load_spec(a.spec)
        for i, step in enumerate(plan(spec), 1):
            print(f'{i:3d}  {step["config"]:28s} rps={step["rps"]:<6} {json.dumps(step["topology"])}')
    elif a.cmd == 'run':
        run(load_spec(a.spec), a.context, a.dry_run, a.exec_pod)
    else:
        out, rows = table(a.results)
        print(f'{len(rows)} runs -> {out}')


if __name__ == '__main__':
    main()
