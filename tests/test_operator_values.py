"""Operator Helm values only use keys that exist in the pinned dynamo-platform 1.4.0 chart."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = yaml.safe_load((ROOT / 'reference/upstream/dynamo-v1.4.0/platform-values.yaml').read_text())
FILES = sorted((ROOT / 'tracks/nvidia-dynamo/install').glob('values-*.yaml'))


def paths(d, prefix=()):
    for k, v in d.items():
        if isinstance(v, dict) and v:
            yield from paths(v, prefix + (k,))
        else:
            yield prefix + (k,)


def exists(path):
    node = CHART
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    return True


@pytest.mark.parametrize('path', FILES, ids=lambda p: p.name)
def test_values_keys_exist_in_pinned_chart(path):
    missing = ['.'.join(p) for p in paths(yaml.safe_load(path.read_text())) if not exists(p)]
    assert not missing, missing


def test_production_values():
    v = yaml.safe_load((ROOT / 'tracks/nvidia-dynamo/install/values-production.yaml').read_text())
    assert v['global']['grove'] == {'install': False, 'enabled': True}
    assert v['global']['etcd']['install'] is False and v['dynamo-operator']['discoveryBackend'] == 'kubernetes'
    assert '@sha256:' in v['dynamo-operator']['controllerManager']['manager']['image']['tag']
    assert v['dynamo-operator']['webhook']['failurePolicy'] == 'Fail'


def test_pinned_chart_versions():
    chart = yaml.safe_load((ROOT / 'reference/upstream/dynamo-v1.4.0/platform-Chart.yaml').read_text())
    deps = {d['name']: d['version'] for d in chart['dependencies']}
    assert chart['version'] == '1.4.0'
    assert deps['grove-charts'] == 'v0.1.0-alpha.12-rc1' and deps['kai-scheduler'] == 'v0.13.4'
