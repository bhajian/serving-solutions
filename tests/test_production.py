"""Production overlays, as `kustomize build` renders them, meet the production bar."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import render_production  # noqa: E402

PROD = ROOT / 'tracks/nvidia-dynamo/production'
OVERLAYS = sorted(p.parent for p in PROD.glob('*-*/*aggregated/kustomization.yaml'))
pytestmark = pytest.mark.skipif(not shutil.which('kustomize'), reason='kustomize not installed')


def build(path):
    out = subprocess.run(['kustomize', 'build', str(path)], capture_output=True, text=True, check=True)
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def pods(docs):
    for d in docs:
        if d['kind'] == 'DynamoGraphDeployment':
            for c in d['spec']['components']:
                yield c['type'], c['podTemplate']['spec']
        elif d['kind'] in ('Deployment', 'Job', 'StatefulSet', 'DaemonSet'):
            yield d['kind'], d['spec']['template']['spec']


def test_overlays_match_the_generator(tmp_path, monkeypatch):
    monkeypatch.setattr(render_production, 'OUT', tmp_path)
    render_production.main()
    for path in sorted(PROD.rglob('*')):
        # operators/ is hand-written (Helm values and the NicClusterPolicy), not generated.
        if path.is_file() and path.name != 'README.md' and 'operators' not in path.relative_to(PROD).parts:
            rel = path.relative_to(PROD)
            assert (tmp_path / rel).exists() and (tmp_path / rel).read_text() == path.read_text(), f'{rel} is stale'


@pytest.mark.parametrize('overlay', OVERLAYS, ids=lambda p: '/'.join(p.parts[-2:]))
def test_production_overlay(overlay):
    docs = build(overlay)
    graph = next(d for d in docs if d['kind'] == 'DynamoGraphDeployment')
    kinds = {d['kind'] for d in docs}
    assert {'NetworkPolicy', 'HTTPRoute', 'SecurityPolicy', 'BackendTrafficPolicy', 'PersistentVolumeClaim'} <= kinds
    assert any(d['kind'] == 'NetworkPolicy' and d['spec']['podSelector'] == {} and
               set(d['spec']['policyTypes']) == {'Ingress', 'Egress'} and 'ingress' not in d['spec']
               for d in docs), 'default-deny NetworkPolicy missing'
    assert graph['metadata']['annotations']['nvidia.com/kai-scheduler-queue']
    for kind, spec in pods(docs):
        assert not spec.get('hostNetwork'), kind
        for c in spec['containers'] + spec.get('initContainers', []):
            assert re.search(r'@sha256:[0-9a-f]{64}$', c['image']), (kind, c['image'])
            assert not c.get('securityContext', {}).get('privileged'), kind
            if kind in ('worker', 'prefill', 'decode') and c['name'] == 'main':
                assert any(k.startswith('rdma/') for k in c['resources']['limits']), 'RDMA via device plugin'
                assert any(e['name'] == 'UCX_NET_DEVICES' for e in c['env'])
                assert spec['nodeSelector']
    frontend = next(c for c in graph['spec']['components'] if c['type'] == 'frontend')
    args = frontend['podTemplate']['spec']['containers'][0]['args']
    assert 'round-robin' not in args and args[args.index('--router-mode') + 1] == 'kv'
    assert frontend['replicas'] >= 2
    if overlay.name == 'disaggregated':
        planner = next(c for c in graph['spec']['components'] if c['type'] == 'planner')
        cm = next(d for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'].endswith('planner-config'))
        config = json.loads(cm['data']['planner_config.json'])
        assert config['optimization_target'] == 'sla' and config['backend'] == 'sglang' and config['mode'] == 'disagg'
        assert planner['podTemplate']['spec']['containers'][0]['args'][-1].endswith('planner_config.json')


def test_no_production_frontend_uses_round_robin_anywhere():
    for path in [*PROD.rglob('*.yaml'), *(ROOT / 'tracks/nvidia-dynamo/graphs').rglob('*.yaml')]:
        text = path.read_text()
        assert not re.search(r'router-mode[ =:"\'\-\s]*round-robin', text), path
        assert 'DYN_ROUTER_MODE' not in text or 'round-robin' not in text, path
