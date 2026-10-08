# Tests

[Home](../README.md) › Tests

Offline checks; no cluster or GPU needed. Run from the repository root:

```bash
python -m pytest -q          # every test below
python tools/validate.py     # strict upstream schema validation of tracks/ and platform/
```

| Area | Test | Guards |
| --- | --- | --- |
| Repository | `test_links.py` | Every relative Markdown link resolves |
| | `test_reference_manifests.py` | Every folder has a README; B300 Compose and Kubernetes tracks stay identical |
| | `test_site_hygiene.py` | No site identifiers in the tree; every `<PLACEHOLDER>` is in `platform/site.env.example` |
| | `test_diagrams.py` | Diagrams are generated from one spec, legible, and every embedded image exists |
| Generated folders | `test_graphs.py` | `tracks/nvidia-dynamo/graphs` match the generator and the measured lab configuration |
| | `test_production.py` | Production overlays match the generator and meet the production bar (needs `kustomize`) |
| | `test_observability.py` | Alerts and dashboards use only metrics with recorded provenance |
| | `test_experiments.py` | Planned studies match the generator, fit the site, and preflight works offline |
| Upstream values | `test_operator_values.py`, `test_nvidia_operators.py`, `test_validate.py` | Helm values use keys that exist in the pinned charts; the validator rejects bad objects |
| | `test_deployments.py` | `tools/render.py` output for every model in `configs/models.yaml` |
| Benchmarks | `test_metrics.py`, `test_streaming.py`, `test_loadgen.py`, `test_long_decode.py`, `test_datasets.py` | Metric definitions, streaming parsing, arrivals and goodput, long-decode analysis, dataset generation |
| | `test_driver_lock.py` | One driver per results directory; every study driver takes the lock |
| | `test_notebook.py` | The compare notebook runs on empty and simulated results |
| Evidence | `test_results_archive.py` | Raw evidence stays in release archives; every study manifest is indexed in its track's `ARCHIVE.md` |
