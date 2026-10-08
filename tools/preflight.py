#!/usr/bin/env python3
"""Check that a cluster is ready for an experiment before spending GPU hours on it.

    python tools/preflight.py tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep --context "$KUBE_CONTEXT"

Reads tracks/nvidia-dynamo/studies/planned/<nn>/experiment.yaml and checks, through kubectl:
  gpus        allocatable nvidia.com/gpu on nodes labelled nvidia.com/gpu.product=NVIDIA-H200
  rdma        allocatable rdma/rdma_shared_device_a on those nodes
  crds        every listed CustomResourceDefinition is installed
  pvcs        every listed PVC in the experiment namespace is Bound
  prometheus  the monitoring namespace has a running Prometheus (Planner, soak)
  images      running serving pods use exactly the pinned image digests (when pods exist)
Exit 0 only when every check passes. The tool never changes the cluster.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

GPU_PRODUCT = 'NVIDIA-H200'
RDMA = 'rdma/rdma_shared_device_a'


def kubectl(context):
    def run(*args):
        out = subprocess.run(['kubectl', '--context', context, *args, '-o', 'json'], capture_output=True, text=True)
        if out.returncode:
            raise RuntimeError(out.stderr.strip()[:300])
        return json.loads(out.stdout)
    return run


def quantity(v):
    return int(str(v).rstrip('k')) if v is not None else 0


def checks(spec, k):
    req, ns, results = spec['requires'], spec['namespace'], []

    def add(name, ok, detail):
        results.append((name, bool(ok), detail))

    nodes = k('get', 'nodes', '-l', f'nvidia.com/gpu.product={GPU_PRODUCT}')['items']
    gpus = sum(quantity(n['status'].get('allocatable', {}).get('nvidia.com/gpu')) for n in nodes)
    add('gpus', gpus >= req.get('gpus', 0), f'{gpus} allocatable on {len(nodes)} {GPU_PRODUCT} nodes, need {req.get("gpus", 0)}')
    if req.get('rdma'):
        rdma = sum(quantity(n['status'].get('allocatable', {}).get(RDMA)) for n in nodes)
        add('rdma', rdma >= req['rdma'], f'{rdma} allocatable {RDMA}, need {req["rdma"]}')
    if req.get('crds'):
        names = {c['metadata']['name'] for c in k('get', 'crd')['items']}
        missing = [c for c in req['crds'] if c not in names]
        add('crds', not missing, 'missing: ' + ', '.join(missing) if missing else f'{len(req["crds"])} present')
    if req.get('pvcs'):
        pvcs = {p['metadata']['name']: p['status'].get('phase') for p in k('-n', ns, 'get', 'pvc')['items']}
        bad = {p: pvcs.get(p, 'absent') for p in req['pvcs'] if pvcs.get(p) != 'Bound'}
        add('pvcs', not bad, f'not Bound: {bad}' if bad else f'{len(req["pvcs"])} Bound')
    if req.get('prometheus'):
        prom = [p for p in k('-n', 'monitoring', 'get', 'pods', '-l', 'app.kubernetes.io/name=prometheus')['items']
                if p['status'].get('phase') == 'Running']
        add('prometheus', prom, f'{len(prom)} running Prometheus pods in monitoring')
    pinned = {i.split('@')[0]: i.split('@')[1] for i in spec.get('images', []) if '@' in i}
    pods = k('-n', ns, 'get', 'pods', '-l', 'nvidia.com/dynamo-graph-deployment-name')['items']
    mismatched = []
    for p in pods:
        for c in p['status'].get('containerStatuses', []):
            repo = c['image'].split('@')[0]
            digest = c.get('imageID', '').split('@')[-1]
            if repo in pinned and digest != pinned[repo]:
                mismatched.append(f'{p["metadata"]["name"]}/{c["name"]}: {digest[:19]}')
    add('images', not mismatched, 'mismatched: ' + '; '.join(mismatched) if mismatched
        else f'{len(pods)} serving pods checked' if pods else 'no serving pods yet (checked after apply)')
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('experiment'); p.add_argument('--context', required=True)
    a = p.parse_args(argv)
    spec = yaml.safe_load((Path(a.experiment) / 'experiment.yaml').read_text())
    results = checks(spec, kubectl(a.context))
    for name, ok, detail in results:
        print(f'{"PASS" if ok else "FAIL"}  {name:11s} {detail}')
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == '__main__':
    sys.exit(main())
