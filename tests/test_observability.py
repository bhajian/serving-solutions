"""Alert rules and dashboards only use metrics with a recorded provenance."""
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
from tools import render_observability  # noqa: E402

OBS = ROOT / 'tracks/nvidia-dynamo/observability'
INVENTORY = {l.strip() for l in (OBS / 'metrics-inventory.txt').read_text().splitlines() if l.strip() and not l.startswith('#')}
SUFFIXES = ('_bucket', '_sum', '_count')
FUNCS = {'histogram_quantile', 'sum', 'rate', 'increase', 'max', 'avg', 'deriv', 'by', 'and', 'unless', 'or', 'le'}


def metrics_in(expr):
    expr = re.sub(r'\{[^}]*\}', '', expr)            # drop label matchers
    expr = re.sub(r'\[[^\]]*\]', '', expr)            # drop range selectors
    expr = re.sub(r'\bby\s*\([^)]*\)', '', expr)       # drop grouping labels
    names = set(re.findall(r'[A-Za-z_:][A-Za-z0-9_:]*', expr)) - FUNCS
    out = set()
    for n in names:
        base = next((n[:-len(s)] for s in SUFFIXES if n.endswith(s) and n[:-len(s)] in INVENTORY), n)
        out.add(base)
    return {n for n in out if not re.fullmatch(r'[0-9e.]+', n)}


def exprs():
    rules = yaml.safe_load((OBS / 'rules.yaml').read_text())
    for g in rules['spec']['groups']:
        for r in g['rules']:
            yield r['alert'], r['expr']
    dash = json.loads((OBS / 'dashboards/dynamo-serving.json').read_text())
    for p in dash['panels']:
        for t in p['targets']:
            yield p['title'], t['expr']


@pytest.mark.parametrize('name,expr', list(exprs()), ids=lambda v: v if isinstance(v, str) and len(v) < 60 else None)
def test_every_metric_has_provenance(name, expr):
    unknown = metrics_in(expr) - INVENTORY
    assert not unknown, f'{name}: {unknown}'


def test_generated_files_are_current(tmp_path, monkeypatch):
    monkeypatch.setattr(render_observability, 'OUT', tmp_path)
    render_observability.main()
    for path in sorted(OBS.rglob('*')):
        if path.is_file() and path.name not in ('README.md', 'metrics-inventory.txt'):
            rel = path.relative_to(OBS)
            assert (tmp_path / rel).read_text() == path.read_text(), f'{rel} is stale'


@pytest.mark.skipif(not shutil.which('promtool'), reason='promtool not installed')
def test_rules_pass_promtool(tmp_path):
    rules = yaml.safe_load((OBS / 'rules.yaml').read_text())
    (tmp_path / 'r.yaml').write_text(yaml.safe_dump({'groups': rules['spec']['groups']}))
    out = subprocess.run(['promtool', 'check', 'rules', str(tmp_path / 'r.yaml')], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_alerts_named_in_troubleshooting_exist():
    names = {r['alert'] for g in yaml.safe_load((OBS / 'rules.yaml').read_text())['spec']['groups'] for r in g['rules']}
    cited = set(re.findall(r'`(Dynamo[A-Za-z]+)`', (ROOT / 'reference/troubleshooting.md').read_text()))
    assert cited <= names, cited - names
