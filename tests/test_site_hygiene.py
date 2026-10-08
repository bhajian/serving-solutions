"""Site identifiers never enter the tree; manifests carry placeholders that render_site fills."""
import ipaddress
import re
import subprocess
from pathlib import Path

import pytest

from tools.render_site import main as render_main

ROOT = Path(__file__).resolve().parents[1]
IPV4 = re.compile(r'(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])')
# 0.0.0.0 / loopback are bind addresses; 2.2.2.2 is Dynamo's built-in placeholder
# bootstrap host for its disaggregated health check (it appears in worker logs).
ALLOWED = {'0.0.0.0', '127.0.0.1', '2.2.2.2'}
DOC_NETS = [ipaddress.ip_network(n) for n in ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24')]
FORBIDDEN = {
    'cloud node hostname': re.compile(r'computeinstance-[a-z0-9]{6,}'),
    'home directory path': re.compile(r'/(?:Users|home)/(?!<)[a-z][a-z0-9_-]+/'),
    'literal kube context': re.compile(r'--context[ =](?!"?\$KUBE_CONTEXT|<)[A-Za-z0-9_.-]+'),
    'Hugging Face token': re.compile(r'hf_[A-Za-z0-9]{30,}'),
    'NGC API key': re.compile(r'nvapi-[A-Za-z0-9_-]{20,}'),
}


def tracked_text():
    names = subprocess.run(['git', 'ls-files', '-co', '--exclude-standard'], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.split('\n')
    for name in filter(None, names):
        path = ROOT / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b'\0' not in data[:8192]:
            yield name, data.decode('utf-8', errors='replace')


def test_no_real_addresses_or_site_identifiers():
    problems = []
    for name, text in tracked_text():
        for raw in IPV4.findall(text):
            try:
                ip = ipaddress.ip_address(raw)
            except ValueError:
                continue  # version strings such as 1.2.3.4567 that are not addresses
            if raw in ALLOWED or any(ip in net for net in DOC_NETS):
                continue
            problems.append(f'{name}: IPv4 address {raw}')
        for label, pattern in FORBIDDEN.items():
            problems += [f'{name}: {label}' for _ in pattern.findall(text)[:1]]
    assert not problems, '\n'.join(sorted(set(problems))[:40])


def test_render_site_substitutes_and_rejects_unknown(tmp_path):
    env = tmp_path / 'site.env'
    env.write_text('NODE_A_HOSTNAME=gpu-a\nNODE_A_IP=192.0.2.10\n')
    src = tmp_path / 'm'; src.mkdir()
    (src / 'w.yaml').write_text('nodeSelector: {kubernetes.io/hostname: <NODE_A_HOSTNAME>}\nip: <NODE_A_IP>\n')
    render_main(['--env', str(env), '--out', str(tmp_path / 'out'), str(src)])
    assert (tmp_path / 'out/m/w.yaml').read_text() == 'nodeSelector: {kubernetes.io/hostname: gpu-a}\nip: 192.0.2.10\n'
    (src / 'x.yaml').write_text('host: <NODE_B_HOSTNAME>\n')
    with pytest.raises(SystemExit, match='NODE_B_HOSTNAME'):
        render_main(['--env', str(env), '--out', str(tmp_path / 'out2'), str(src)])


def test_render_site_refuses_unfilled_env(tmp_path):
    env = tmp_path / 'site.env'
    env.write_text('NODE_A_HOSTNAME=<node-a-name>\n')
    with pytest.raises(SystemExit, match='Fill in'):
        render_main(['--env', str(env), str(tmp_path)])


def test_example_env_covers_every_manifest_placeholder():
    example = (ROOT / 'platform/site.env.example').read_text()
    keys = set(re.findall(r'^([A-Z][A-Z0-9_]+)=', example, re.M))
    used = set()
    for path in [*(ROOT / 'tracks').rglob('*.yaml'), *(ROOT / 'platform').rglob('*.yaml')]:
        used |= set(re.findall(r'<([A-Z][A-Z0-9_]+)>', path.read_text()))
    assert used <= keys, used - keys
