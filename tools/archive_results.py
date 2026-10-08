#!/usr/bin/env python3
"""Move raw benchmark evidence out of the tree into per-study tarballs, or restore it.

The repository keeps what the notebooks read (CSV tables, summary/metadata JSON,
Markdown). Raw evidence (streaming JSONL, Prometheus snapshots, logs, rendered
charts, executed notebooks) goes into build/archives/<study>.tar.gz, published as a
GitHub release asset. Each study keeps ARCHIVE-MANIFEST.sha256 in the tree, so a
downloaded archive can be verified file by file.

    python tools/archive_results.py pack                 # writes archives, removes raw files
    python tools/archive_results.py restore --from DIR   # extracts and verifies archives
"""
import argparse
import hashlib
import io
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY_ROOTS = ROOT / 'tracks'  # completed studies: tracks/<track>/studies/<study>/
ARCHIVES = ROOT / 'build/archives'
RAW_SUFFIXES = {'.prom', '.jsonl', '.log', '.png'}
MANIFEST = 'ARCHIVE-MANIFEST.sha256'


def is_raw(path):
    return path.suffix in RAW_SUFFIXES or path.name.endswith('.executed.ipynb')


def studies():
    return sorted(p for p in STUDY_ROOTS.glob('*/studies/*') if p.is_dir() and p.name != 'planned')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def pack():
    ARCHIVES.mkdir(parents=True, exist_ok=True)
    for study in studies():
        raw = sorted(p for p in study.rglob('*') if p.is_file() and is_raw(p))
        if not raw:
            continue
        lines, target = [], ARCHIVES / f'{study.name}.tar.gz'
        with tarfile.open(target, 'w:gz') as tar:
            for p in raw:
                data = p.read_bytes()
                rel = p.relative_to(study).as_posix()
                lines.append(f'{sha256(data)}  {rel}')
                info = tarfile.TarInfo(f'{study.name}/{rel}'); info.size = len(data); info.mtime = 0
                tar.addfile(info, io.BytesIO(data))
        (study / MANIFEST).write_text('\n'.join(lines) + '\n')
        for p in raw:
            p.unlink()
        print(f'{study.name}: {len(raw)} files -> {target.relative_to(ROOT)} '
              f'({target.stat().st_size / 1e6:.1f} MB, sha256 {sha256(target.read_bytes())})')


def restore(source):
    for study in studies():
        manifest = study / MANIFEST
        if not manifest.exists():
            continue
        expected = dict(reversed(line.split('  ', 1)) for line in manifest.read_text().splitlines() if line)
        with tarfile.open(Path(source) / f'{study.name}.tar.gz') as tar:
            for member in tar.getmembers():
                rel = member.name.split('/', 1)[1]
                data = tar.extractfile(member).read()
                if expected.get(rel) != sha256(data):
                    raise SystemExit(f'{study.name}/{rel}: checksum mismatch')
                (study / rel).parent.mkdir(parents=True, exist_ok=True)
                (study / rel).write_bytes(data)
        print(f'{study.name}: restored and verified {len(expected)} files')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('pack')
    r = sub.add_parser('restore'); r.add_argument('--from', dest='source', default=str(ARCHIVES))
    a = p.parse_args(argv)
    pack() if a.cmd == 'pack' else restore(a.source)


if __name__ == '__main__':
    sys.exit(main())
