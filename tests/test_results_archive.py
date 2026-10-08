"""Raw evidence stays in release archives; the tree keeps what notebooks read."""
import re
import subprocess
from pathlib import Path

from tools.archive_results import MANIFEST, is_raw

ROOT = Path(__file__).resolve().parents[1]


def tracked(prefix):
    out = subprocess.run(['git', 'ls-files', prefix], cwd=ROOT, capture_output=True, text=True, check=True)
    return [Path(p) for p in out.stdout.split()]


def test_no_raw_evidence_tracked_in_studies():
    raw = [str(p) for p in tracked('tracks') if is_raw(p) and 'studies' in p.parts]
    assert not raw, raw[:10]


def test_archive_manifests_are_well_formed_and_indexed():
    manifests = sorted(ROOT.glob(f'tracks/*/studies/*/{MANIFEST}'))
    assert manifests
    for manifest in manifests:
        lines = manifest.read_text().splitlines()
        assert lines and all(re.fullmatch(r'[0-9a-f]{64}  \S.*', line) for line in lines), manifest
        assert all(is_raw(Path(line.split('  ', 1)[1])) for line in lines), manifest
        index = (manifest.parent.parent / 'ARCHIVE.md').read_text()  # one archive index per track
        assert f'{manifest.parent.name}.tar.gz' in index, manifest.parent.name
