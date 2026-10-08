"""Consistency checks for the hand-written B300 reference deployments (tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-03).

The reference files are written for humans, so nothing regenerates them. These
tests make sure they stay consistent with each other and with the flags that
tools/render.py produces for the same model profile.
"""
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE = dict(line.split('=', 1) for line in (ROOT / 'tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env.example').read_text().splitlines()
            if line and not line.startswith('#'))

# (folder, engine, topology)
TRACKS = [
    ('tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm', 'vllm', 'agg'),
    ('tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/sglang', 'sglang', 'agg'),
    ('tracks/nvidia-dynamo/sites/hgx-b300-2x8/02-dynamo-disagg-vllm', 'vllm', 'disagg'),
    ('tracks/nvidia-dynamo/sites/hgx-b300-2x8/03-dynamo-disagg-sglang', 'sglang', 'disagg'),
]
DISAGG_FLAGS = {'--disaggregation-mode', '--kv-transfer-config',
                '--disaggregation-transfer-backend', '--disaggregation-bootstrap-port'}


def platform_dir(folder, platform):
    """Kubernetes manifests sit in the site folder; Compose files in its compose/ subfolder."""
    if platform == 'kubernetes':
        return ROOT / folder
    return ROOT / folder.replace('tracks/nvidia-dynamo/sites/hgx-b300-2x8/', 'tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/')


def interpolate(text):
    return re.sub(r'\$\{(\w+)\}', lambda m: SITE[m.group(1)], text)


def compose(folder, node):
    return yaml.safe_load(interpolate((platform_dir(folder, 'docker') / f'node-{node}.yaml').read_text()))


def k8s(folder, name):
    return next(yaml.safe_load_all((platform_dir(folder, 'kubernetes') / name).read_text()))


def normalize(value):
    """Compare meaning, not formatting: JSON spacing and 0.80 vs 0.8."""
    if isinstance(value, str) and value.startswith('{'):
        return json.loads(value)
    if isinstance(value, str) and re.fullmatch(r'\d+\.\d+', value):
        return float(value)
    return value


def flags_from_script(script):
    tokens = shlex.split(script.split('exec ', 1)[1].replace('\\\n', ' '))
    args = tokens[3:]  # drop: python3 -m dynamo.<engine>
    pairs, i = {}, 0
    while i < len(args):
        if i + 1 < len(args) and not args[i + 1].startswith('--'):
            pairs[args[i]] = normalize(args[i + 1]); i += 2
        else:
            pairs[args[i]] = True; i += 1
    return pairs


def compose_workers(folder):
    a, b = compose(folder, 'a')['services'], compose(folder, 'b')['services']
    worker_a = next(v for k, v in a.items() if k not in ('etcd', 'frontend'))
    worker_b = next(iter(b.values()))
    return worker_a, worker_b


def k8s_containers(folder):
    d = platform_dir(folder, 'kubernetes')
    return [yaml.safe_load(p.read_text())['spec']['template']['spec']['containers'][0]
            for p in sorted(d.glob('3*.yaml'))]


@pytest.mark.parametrize('folder,engine,topology', TRACKS)
def test_compose_and_kubernetes_launch_identical_engines(folder, engine, topology):
    wa, wb = compose_workers(folder)
    fa, fb = flags_from_script(wa['command'][0]), flags_from_script(wb['command'][0])
    containers = k8s_containers(folder)
    k8s_flags = [flags_from_script(c['args'][0]) for c in containers]
    if topology == 'agg':
        assert fa == fb == k8s_flags[0]
        assert not DISAGG_FLAGS & set(fa)
    else:
        assert fa['--disaggregation-mode'] == 'prefill' and fb['--disaggregation-mode'] == 'decode'
        assert {**fa, '--disaggregation-mode': 'decode'} == fb
        assert k8s_flags == [fa, fb]
    for script in [wa['command'][0], wb['command'][0], *(c['args'][0] for c in containers)]:
        assert 'dynamo.' + engine in script
        subprocess.run(['bash', '-n'], input=script, text=True, check=True)


@pytest.mark.parametrize('engine', ['vllm', 'sglang'])
def test_aggregated_equals_disaggregated_minus_transfer_flags(engine):
    agg = flags_from_script(compose_workers(f'tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/{engine}')[0]['command'][0])
    dis = flags_from_script(compose_workers(f'tracks/nvidia-dynamo/sites/hgx-b300-2x8/0{2 if engine == "vllm" else 3}-dynamo-disagg-{engine}')[0]['command'][0])
    assert agg == {k: v for k, v in dis.items() if k not in DISAGG_FLAGS}


@pytest.mark.parametrize('folder,engine', [(f, e) for f, e, t in TRACKS if t == 'disagg'])
def test_disaggregated_matches_render_tool(tmp_path, folder, engine):
    subprocess.run([sys.executable, str(ROOT / 'tools/render.py'), '--target', 'compose',
                    '--backend', engine, '--model', 'nemotron-ultra', '--out', str(tmp_path)],
                   check=True, capture_output=True)
    for node, role in [('a', 'prefill'), ('b', 'decode')]:
        rendered = yaml.safe_load((tmp_path / f'node-{node}.yaml').read_text())['services'][role]
        cmd = rendered['entrypoint']
        args = cmd[cmd.index('dynamo.' + engine) + 1:]
        expected = flags_from_script('exec python3 -m dynamo.x ' + shlex.join(args))
        written = compose(folder, node)['services'][role]
        assert flags_from_script(written['command'][0]) == expected
        skip = {'DYN_NAMESPACE', 'DYN_TCP_RESPONSE_STREAM_HOST', 'VLLM_HTTP_TIMEOUT_KEEP_ALIVE'}
        for key, value in rendered['environment'].items():
            if key not in skip:
                assert str(written['environment'][key]) == str(value), key


@pytest.mark.parametrize('folder,engine,topology', TRACKS)
def test_control_plane_and_transfer_settings(folder, engine, topology):
    services = compose(folder, 'a')['services']
    assert {'etcd', 'frontend'} <= set(services)
    front = services['frontend']['entrypoint']
    worker = flags_from_script(compose_workers(folder)[0]['command'][0])
    block = worker['--block-size' if engine == 'vllm' else '--page-size']
    assert f'--kv-cache-block-size={block}' in front
    k8s_front = k8s(folder, '20-frontend.yaml')['spec']['template']['spec']['containers'][0]['command']
    assert f'--kv-cache-block-size={block}' in k8s_front
    for w in compose_workers(folder):
        rdma = '/dev/infiniband:/dev/infiniband' in w.get('devices', [])
        assert rdma == (topology == 'disagg')
        assert ('UCX_NET_DEVICES' in w['environment']) == (topology == 'disagg')
    for c in k8s_containers(folder):
        assert c['securityContext'].get('privileged', False) == (topology == 'disagg')


def test_no_reference_file_sets_the_broken_response_stream_host():
    for path in [*ROOT.glob('tracks/**/*.yaml'), *ROOT.glob('platform/**/*.yaml'), ROOT / 'tools/render.py']:
        text = path.read_text()
        for line in text.splitlines():
            if 'DYN_TCP_RESPONSE_STREAM_HOST' in line:
                assert line.strip().startswith('#'), f'{path}: {line}'


@pytest.mark.parametrize('folder,engine,topology', TRACKS)
def test_run_records_and_kustomizations(folder, engine, topology):
    for platform, suffix in [('docker', 'compose'), ('kubernetes', 'k8s')]:
        record = json.loads((platform_dir(folder, platform) / 'deployment.json').read_text())
        assert record['technology'] == f'dynamo-{topology}-{suffix}'
        assert record['backend'] == engine
        worker = flags_from_script(compose_workers(folder)[0]['command'][0])
        assert record['model']['model_id'] == worker['--served-model-name']
        assert record['max_model_len'] == int(worker['--max-model-len' if engine == 'vllm' else '--context-length'])
    kdir = platform_dir(folder, 'kubernetes')
    resources = yaml.safe_load((kdir / 'kustomization.yaml').read_text())['resources']
    assert resources == sorted(p.name for p in kdir.glob('[0-9]*.yaml'))
    namespaces = {d['metadata']['namespace'] for r in resources[1:]
                  for d in yaml.safe_load_all((kdir / r).read_text()) if d}
    assert namespaces == {yaml.safe_load((kdir / resources[0]).read_text())['metadata']['name']}


def inside_completed_study(parts):
    if 'studies' not in parts:
        return False
    i = parts.index('studies')
    return len(parts) > i + 2 and parts[i + 1] != 'planned'


def test_every_folder_has_a_readme():
    skip = {'.git', '.venv', '__pycache__', '.pytest_cache', 'build', 'results', 'router'}
    missing = [str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_dir()
               and not skip & set(p.relative_to(ROOT).parts)
               and p.relative_to(ROOT).parts[:2] != ('datasets', 'generated')
               # as-measured/ is one documented record; its per-file folders need no README
               and 'as-measured' not in p.relative_to(ROOT).parts[:-1]
               # a completed study's run, analysis and record folders are documented by the study README
               and not inside_completed_study(p.relative_to(ROOT).parts)
               and not (p / 'README.md').exists()]
    assert not missing, missing
