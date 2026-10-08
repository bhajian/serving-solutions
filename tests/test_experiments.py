"""Prepared experiments are complete, consistent with the hardware, and preflight works offline."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import preflight, render_experiments  # noqa: E402

EXP = ROOT / 'tracks/nvidia-dynamo/studies/planned'
FOLDERS = sorted(p for p in EXP.iterdir() if p.is_dir() and p.name[:2].isdigit())
CONFIGS = sorted(p.parent for p in EXP.glob('*/configs/*/kustomization.yaml'))


def test_experiments_match_the_generator(tmp_path, monkeypatch):
    monkeypatch.setattr(render_experiments, 'OUT', tmp_path)
    render_experiments.render()
    for path in sorted(EXP.rglob('*')):
        if path.is_file() and path.suffix in ('.yaml', '.md') and path.name not in ('sample_memory.py',):
            rel = path.relative_to(EXP)
            assert (tmp_path / rel).exists() and (tmp_path / rel).read_text() == path.read_text(), f'{rel} is stale'


@pytest.mark.parametrize('folder', FOLDERS, ids=lambda p: p.name)
def test_every_experiment_is_ready_to_run(folder):
    for name in ('README.md', 'READY.md', 'experiment.yaml'):
        assert (folder / name).exists(), name
    readme = (folder / 'README.md').read_text()
    for section in ('**Objective.**', '**Hypothesis.**', '## Dataset', '## Run', '## Success criteria', 'Planning estimate'):
        assert section in readme, section
    assert 'UNVALIDATED' in readme
    sweep = folder / 'sweep.yaml'
    if sweep.exists():
        spec = yaml.safe_load(sweep.read_text())
        for c in spec['configs']:
            assert (ROOT / c['overlay'].replace('build/site/', '')).exists(), c['overlay']


@pytest.mark.skipif(not shutil.which('kustomize'), reason='kustomize not installed')
@pytest.mark.parametrize('config', CONFIGS, ids=lambda p: f'{p.parts[-3]}/{p.name}')
def test_layout_fits_the_site_and_tp_matches_gpus(config):
    out = subprocess.run(['kustomize', 'build', str(config)], capture_output=True, text=True, check=True).stdout
    graph = next(d for d in yaml.safe_load_all(out) if d and d['kind'] == 'DynamoGraphDeployment')
    total = 0
    for c in graph['spec']['components']:
        if c['type'] in ('worker', 'prefill', 'decode'):
            main = c['podTemplate']['spec']['containers'][0]
            args, gpus = main['args'], int(main['resources']['limits']['nvidia.com/gpu'])
            tp = int(args[args.index('--tensor-parallel-size') + 1])
            assert tp == gpus, f'{c["name"]}: TP {tp} on {gpus} GPUs'
            assert gpus <= 8, 'a worker must fit on one 8-GPU node'
            total += gpus * c['replicas']
    assert total <= 16, f'{config.name} uses {total} GPUs on a 16-GPU site'


def fake(responses):
    def run(*args):
        key = ' '.join(a for a in args if not a.startswith('-l') and a not in ('-n',))
        for k, v in responses.items():
            if k in ' '.join(args):
                return v
        raise RuntimeError(f'unexpected kubectl {args}')
    return run


def node(gpus, rdma):
    return {'status': {'allocatable': {'nvidia.com/gpu': str(gpus), 'rdma/rdma_shared_device_a': str(rdma)}}}


def test_preflight_passes_and_fails_on_recorded_cluster_state():
    spec = {'namespace': 'nemotron-3-nano', 'images': ['nvcr.io/x/sglang-runtime:1.4.0@sha256:aaa'],
            'requires': {'gpus': 16, 'rdma': 16, 'crds': ['dynamographdeployments.nvidia.com'],
                         'pvcs': ['model-weights'], 'prometheus': True}}
    good = {'get nodes': {'items': [node(8, 63), node(8, 63)]},
            'get crd': {'items': [{'metadata': {'name': 'dynamographdeployments.nvidia.com'}}]},
            'get pvc': {'items': [{'metadata': {'name': 'model-weights'}, 'status': {'phase': 'Bound'}}]},
            'monitoring get pods': {'items': [{'status': {'phase': 'Running'}}]},
            'nemotron-3-nano get pods': {'items': [{'metadata': {'name': 'w'}, 'status': {'containerStatuses': [
                {'name': 'main', 'image': 'nvcr.io/x/sglang-runtime:1.4.0@sha256:aaa', 'imageID': 'nvcr.io/x/sglang-runtime@sha256:aaa'}]}}]}}
    assert all(ok for _, ok, _ in preflight.checks(spec, fake(good)))
    bad = dict(good, **{'get nodes': {'items': [node(8, 0)]},
                        'get pvc': {'items': [{'metadata': {'name': 'model-weights'}, 'status': {'phase': 'Pending'}}]},
                        'nemotron-3-nano get pods': {'items': [{'metadata': {'name': 'w'}, 'status': {'containerStatuses': [
                            {'name': 'main', 'image': 'nvcr.io/x/sglang-runtime:1.4.0', 'imageID': 'x@sha256:bbb'}]}}]}})
    failed = {name for name, ok, _ in preflight.checks(spec, fake(bad)) if not ok}
    assert failed == {'gpus', 'rdma', 'pvcs', 'images'}
