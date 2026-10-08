#!/usr/bin/env python3
"""Substitute <PLACEHOLDER> site values into manifests, writing copies under --out.

Checked-in manifests never contain real hostnames or addresses; render them for a
specific cluster with a git-ignored env file (see platform/site.env.example).
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r'<([A-Z][A-Z0-9_]+)>')
SUFFIXES = {'.yaml', '.yml', '.json', '.env', '.sh'}


def load_env(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            key, _, value = line.partition('=')
            values[key.strip()] = value.strip()
    unset = [k for k, v in values.items() if not v or TOKEN.fullmatch(v) or v.startswith('<')]
    if unset:
        raise SystemExit(f'Fill in these values in {path}: {", ".join(unset)}')
    return values


def render(text, values, source):
    missing = sorted({m for m in TOKEN.findall(text) if m not in values})
    if missing:
        raise SystemExit(f'{source}: unknown placeholders {missing}; add them to the env file')
    return TOKEN.sub(lambda m: values[m.group(1)], text)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--env', required=True, help='Site env file, e.g. platform/site.env')
    p.add_argument('--out', default=str(ROOT / 'build/site'))
    p.add_argument('paths', nargs='+', help='Files or directories to render')
    a = p.parse_args(argv)
    values = load_env(a.env)
    out = Path(a.out)
    count = 0
    for target in map(Path, a.paths):
        files = [target] if target.is_file() else sorted(f for f in target.rglob('*') if f.suffix in SUFFIXES)
        base = target.parent
        for f in files:
            dest = out / f.resolve().relative_to(base.resolve())
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(render(f.read_text(), values, f))
            count += 1
    print(f'rendered {count} files into {out}')


if __name__ == '__main__':
    sys.exit(main())
