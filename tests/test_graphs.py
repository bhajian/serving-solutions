"""Operator graphs (tracks/nvidia-dynamo/graphs) stay tied to the measured lab configuration."""
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import render_graphs  # noqa: E402

LAB = ROOT / 'tracks/nvidia-dynamo/sites/nebius-h200-2x8'
MEASURED = {  # (model, topology) -> as-measured worker manifest
    ('nemotron-3-nano', 'aggregated'): 'nemotron-3-nano/lab/as-measured/workers-tp4-aggregated/40-workers-tp4.yaml',
    ('nemotron-3-nano', 'disaggregated'): 'nemotron-3-nano/lab/as-measured/workers-tp4-disaggregated/40-workers-tp4-disaggregated.yaml',
    ('deepseek-v4-pro', 'aggregated'): 'deepseek-v4-pro/lab/as-measured/workers-tp8-aggregated/40-workers.yaml',
    ('deepseek-v4-pro', 'disaggregated'): 'deepseek-v4-pro/lab/as-measured/workers-tp8-disaggregated/40-workers-disaggregated.yaml',
}
GRAPHS = sorted(ROOT.glob('tracks/nvidia-dynamo/graphs/*/*/graph.yaml'))
# Flags the operator graph may change relative to the lab, beyond MITIGATIONS.
ALLOWED = {'--gc-threshold', '--kv-events-config', '--max-running-requests', '--cuda-graph-max-bs-decode',
           '--bucket-inter-token-latency'}


def flags(args):
    out, i = {}, 0
    while i < len(args):
        if args[i].startswith('--'):
            vals = []
            j = i + 1
            while j < len(args) and not args[j].startswith('--'):
                vals.append(args[j]); j += 1
            out[args[i]] = tuple(vals)
            i = j
        else:
            i += 1
    return out


def lab_workers(model, topology):
    docs = [d for d in yaml.safe_load_all((LAB / MEASURED[(model, topology)]).read_text()) if d]
    by_role = {}
    for d in docs:
        cmd = d['spec']['template']['spec']['containers'][0]['command']
        role = d['metadata']['labels']['serving-role']
        by_role.setdefault({'aggregated': 'worker'}.get(role, role), flags(cmd[cmd.index('dynamo.sglang') + 1:]))
    return by_role


def load(path):
    return yaml.safe_load(path.read_text())


def test_graphs_match_the_generator(tmp_path, monkeypatch):
    monkeypatch.setattr(render_graphs, 'OUT', tmp_path)
    render_graphs.main()
    for path in GRAPHS:
        rel = path.relative_to(ROOT / 'tracks/nvidia-dynamo/graphs')
        assert (tmp_path / rel).read_text() == path.read_text(), f'{rel} is stale; run tools/render_graphs.py'


@pytest.mark.parametrize('model,topology', sorted(MEASURED))
def test_engine_flags_equal_measured_except_documented_mitigations(model, topology):
    g = load(ROOT / f'tracks/nvidia-dynamo/graphs/{model}/{topology}/graph.yaml')
    lab = lab_workers(model, topology)
    for c in g['spec']['components']:
        if c['type'] == 'frontend':
            continue
        ours = flags(c['podTemplate']['spec']['containers'][0]['args'])
        theirs = lab[c['type']]
        changed = {k for k in set(ours) | set(theirs) if ours.get(k) != theirs.get(k)}
        assert changed <= ALLOWED, f'{model}/{topology}/{c["name"]}: undocumented flag changes {changed - ALLOWED}'


def test_topologies_share_one_graph_name_and_frontend():
    for model in {p.parts[-3] for p in GRAPHS}:
        agg = load(ROOT / f'tracks/nvidia-dynamo/graphs/{model}/aggregated/graph.yaml')
        dis = load(ROOT / f'tracks/nvidia-dynamo/graphs/{model}/disaggregated/graph.yaml')
        assert agg['metadata']['name'] == dis['metadata']['name'] == model
        types = lambda g: sorted(c['type'] for c in g['spec']['components'])
        assert types(agg) == ['frontend', 'worker'] and types(dis) == ['decode', 'frontend', 'prefill']


@pytest.mark.parametrize('path', GRAPHS, ids=lambda p: '/'.join(p.parts[-3:-1]))
def test_production_hygiene(path):
    g = load(path)
    for c in g['spec']['components']:
        spec = c['podTemplate']['spec']
        assert not spec.get('hostNetwork')
        for ctr in spec['containers'] + spec.get('initContainers', []):
            assert re.search(r'@sha256:[0-9a-f]{64}$', ctr['image']), ctr['image']
            assert not ctr.get('securityContext', {}).get('privileged')
        main = spec['containers'][0]
        assert 'memory' in main['resources']['limits'], f'{c["name"]}: host memory limit required'
        if c['type'] == 'frontend':
            args = main['args']
            assert args[args.index('--router-mode') + 1] == 'kv'
            assert main['readinessProbe']['exec'] and main['livenessProbe']['exec']
            assert c['replicas'] >= 2
        else:
            assert main['startupProbe']['failureThreshold'] * main['startupProbe']['periodSeconds'] >= 3600
            live = main['livenessProbe']
            assert live['failureThreshold'] * live['periodSeconds'] >= 120, 'liveness too aggressive for long prefills'


def test_prefill_memory_limit_has_headroom_over_observed_peak():
    g = load(ROOT / 'tracks/nvidia-dynamo/graphs/nemotron-3-nano/disaggregated/graph.yaml')
    prefill = next(c for c in g['spec']['components'] if c['type'] == 'prefill')
    limit = prefill['podTemplate']['spec']['containers'][0]['resources']['limits']['memory']
    assert int(limit.rstrip('Gi')) >= 308 * 1.4, 'observed prefill peak was 308 GiB'
