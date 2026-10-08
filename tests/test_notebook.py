"""Execute the report with empty and simulated results in temporary directories."""
import json
from pathlib import Path

import nbformat
from nbclient import NotebookClient
import pytest

from benchmarks.metrics import request_metrics, summarize
from benchmarks.run import write_csv

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('with_data', [False, True])
def test_notebook_executes(tmp_path, with_data):
    if with_data:
        for i, tech in enumerate(['dynamo-compose', 'dynamo-k8s', 'llmd-k8s', 'llmd-k8s']):
            for repeat in range(2):
                run_id = f'fixture-{i}-{repeat}'
                out = tmp_path / run_id; out.mkdir()
                row = dict(request_metrics([{'time_s': t, 'token_count': 1} for t in [1, 1.2, 1.4]], 1.5, 3),
                           success=True, measurement_valid=True, prompt_tokens=256000, completion_tokens=3,
                           first_content_ms=1000, client_queue_ms=0, run_id=run_id)
                summary = summarize([row], 2)
                summary.update(run_id=run_id, model='fixture/model', technology=tech, workload='chatbot',
                    concurrency=1, max_model_len=262144, requested_output_tokens=512, min_input_tokens=250001,
                    cache_state='uncontrolled', temperature=0, session_rate=0, think_time_s=0,
                    dataset_sha256='synthetic-fixture-not-a-benchmark', extra_body_json='{}', image='test:fixture',
                    model_revision='fixture-revision', deployment_sha256=f'fixture-config-{i}')
                if i == 3:
                    summary['backend'] = 'sglang'
                write_csv(out / 'summary.csv', [summary])
                write_csv(out / 'requests.csv', [{k: v for k, v in row.items() if not isinstance(v, (dict, list))}])
    nb = nbformat.read(ROOT / 'benchmarks/compare.ipynb', as_version=4)
    nb.cells.insert(0, nbformat.v4.new_code_cell('import os\nos.environ["DISAGG_RESULTS"] = ' + repr(str(tmp_path))))
    NotebookClient(nb, timeout=120, kernel_name='python3', resources={'metadata': {'path': str(ROOT)}}).execute()
    nbformat.write(nb, tmp_path / 'executed.ipynb')
    if with_data:
        import pandas as pd
        comparison = pd.read_csv(tmp_path / 'analysis/comparison-cohort-0.csv')
        assert len(comparison) == 4
        assert set(comparison[comparison.technology == 'llmd-k8s'].backend) == {'vllm', 'sglang'}
        assert set(comparison.repeats) == {2}
        assert (tmp_path / 'analysis/comparison-cohort-0.png').is_file()
