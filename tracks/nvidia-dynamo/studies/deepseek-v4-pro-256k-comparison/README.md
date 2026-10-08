# DeepSeek V4 Pro 256K comparison — 30 September 2026

> Raw evidence (streaming JSONL, worker-metric snapshots, logs, charts and the
> executed notebook) is in this study's release archive; see [ARCHIVE.md](../ARCHIVE.md).
> `ARCHIVE-MANIFEST.sha256` lists every archived file with its checksum.

Saved measurements from the same checkpoint on 16 H200 GPUs, comparing one TP8
prefill worker plus one TP8 decode worker against two TP8 aggregated replicas.
See the [report and protocol](REPORT.md)
for the configuration, dataset hashes, reproduction steps and limitations.

| Measured run | Topology | Requests | Wall time |
| --- | --- | ---: | ---: |
| `20260930T223415Z-e8ee09b4/` | Disaggregated, 1P + 1D | 24 | 782.50 s |
| `20260930T225241Z-a4a27eae/` | Aggregated, 2 replicas | 24 | 141.45 s |

All 48 requests passed. The paired request bodies were identical. Aggregated
follow-ups reused their long prefixes; disaggregated follow-ups reprocessed them
under concurrency. The cause of that cache behavior remains undiagnosed. This
single-run comparison does not establish a universal topology ranking.

- Each measured run contains request records, summaries, deployment metadata,
  dataset metadata and worker metrics before and after the run.
- `analysis/` contains the executed notebook (`analysis/deepseek_v4_pro_256k.executed.ipynb`, archived),
  exported tables and charts. The editable [source notebook](deepseek_v4_pro_256k.ipynb)
  reads this archive directly; no cluster or dataset download is needed for analysis.
- `study-records/` contains benchmark commands, cache-clear acknowledgements,
  logs and completion records.
- `diagnostics/` contains pilots, the interrupted calibration and worker logs.
  These are excluded from the measured comparison.
- `reproduction/` contains configuration snapshots, scripts and GPU inventory.

Generated datasets and model weights are not included. The dataset metadata
records generation parameters and hashes. This archive is an explicit exception
to the repository's default ignore rule for benchmark output.
