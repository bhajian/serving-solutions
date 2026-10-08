"""Only one benchmark driver may run per results directory; flush evidence is append-only."""
import json
import multiprocessing
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.driver_lock import EVIDENCE, DriverBusy, acquire, append_evidence

ROOT = Path(__file__).resolve().parents[1]


def test_second_driver_is_refused_until_first_exits(tmp_path):
    first = acquire(tmp_path)
    # A separate process models the duplicate driver seen in the 8K/128K study.
    code = 'import sys; from benchmarks.driver_lock import acquire, DriverBusy\n' \
           f'try:\n    acquire({str(tmp_path)!r})\nexcept DriverBusy:\n    sys.exit(3)\n'
    assert subprocess.run([sys.executable, '-c', code], cwd=ROOT).returncode == 3
    first.close()
    assert subprocess.run([sys.executable, '-c', code], cwd=ROOT).returncode == 0
    with pytest.raises(DriverBusy):
        held = acquire(tmp_path)
        acquire(tmp_path)
    held.close()


def _writer(path, n, tag):
    for i in range(n):
        append_evidence(path, {'writer': tag, 'i': i})


def test_evidence_is_appended_never_truncated(tmp_path):
    append_evidence(tmp_path, {'writer': 'existing', 'i': 0})
    procs = [multiprocessing.Process(target=_writer, args=(tmp_path, 200, t)) for t in ('a', 'b')]
    for p in procs: p.start()
    for p in procs: p.join()
    lines = [json.loads(l) for l in (tmp_path / EVIDENCE).read_text().splitlines()]
    assert len(lines) == 401 and lines[0]['writer'] == 'existing'
    assert all('utc' in l and 'pid' in l for l in lines)


@pytest.mark.parametrize('driver', sorted(ROOT.glob('tracks/*/studies/*/benchmark_*.py')),
                         ids=lambda p: p.name)
def test_every_driver_takes_the_lock_and_appends(driver):
    text = driver.read_text()
    assert 'acquire(logdir)' in text and "cache-clear.log').open('a')" in text and 'BENCH_RUN_LABEL' in text
