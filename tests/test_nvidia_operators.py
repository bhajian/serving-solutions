"""GPU/Network Operator values use keys that exist in the pinned charts."""
from pathlib import Path

import pytest
import yaml

from tests.test_operator_values import paths

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / 'platform/operators'
CHARTS = {'gpu-operator-values.yaml': 'gpu-operator-v26.7.1-values.yaml',
          'network-operator-values.yaml': 'network-operator-v26.7.0-values.yaml'}


@pytest.mark.parametrize('ours,theirs', CHARTS.items())
def test_keys_exist_in_pinned_chart(ours, theirs):
    chart = yaml.safe_load((ROOT / 'reference/upstream/nvidia-operators' / theirs).read_text())
    missing = []
    for path in paths(yaml.safe_load((OPS / ours).read_text())):
        node = chart
        for key in path:
            if not isinstance(node, dict) or key not in node:
                missing.append('.'.join(path)); break
            node = node[key]
    assert not missing, missing


def test_rdma_resource_matches_graph_patches():
    import json, sys
    sys.path.insert(0, str(ROOT))
    from tools.render_production import SITES
    policy = yaml.safe_load((OPS / 'nic-cluster-policy.yaml').read_text())
    names = [c['resourceName'] for c in json.loads(policy['spec']['rdmaSharedDevicePlugin']['config'])['configList']]
    assert SITES['h200']['rdma_resource'] == f'rdma/{names[0]}'
