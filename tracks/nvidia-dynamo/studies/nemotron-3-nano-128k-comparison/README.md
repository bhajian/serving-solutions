# Nemotron 3 Nano 128K comparison — 30 September 2026

> Raw evidence (streaming JSONL, worker-metric snapshots, logs, charts and the
> executed notebook) is in this study's release archive; see [ARCHIVE.md](../ARCHIVE.md).
> `ARCHIVE-MANIFEST.sha256` lists every archived file with its checksum.

Six measured runs on the same 16 H200 GPUs and pinned BF16 checkpoint: three
runs with one TP8 prefill plus one TP8 decode worker, followed by three runs with
two TP8 aggregated replicas. Every run replays the same 32 three-turn sessions
at concurrency four, with roughly 128K input tokens and up to 256 output tokens.

**576/576 requests passed.** Aggregated averaged 65.09 seconds per run versus
105.48 seconds for disaggregated: 1.62× faster for this workload. Total measured
time was 8.53 minutes. Disaggregated reported prefix-cache hits on 192/192
follow-ups; aggregated reported hits on 190/192. This is a fixed-allocation,
fixed-order comparison, not a GPU-sizing or maximum-capacity study.

See the [full report and protocol](REPORT.md)
for settings, run IDs, interpretation and reproduction instructions.

- Timestamped run directories contain streaming records, request CSVs,
  summaries, metadata and the four before/after worker-metric snapshots per run.
- executed notebook (`analysis/nemotron_3_nano_128k.executed.ipynb`, archived) and exported
  PNG/CSV comparisons are in `analysis/`. The [source notebook](nemotron_3_nano_128k.ipynb)
  reads this archive without cluster access or the generated dataset.
- `comparison-audit.json` records the reported comparison values.
- `study-records/` contains commands, cache-reset acknowledgements, logs and
  completion status for each measured repeat.
- `diagnostics/` contains excluded pilots, worker logs, public API smoke checks
  and the separate 128,014-token retrieval check.
- `reproduction/` contains model/runtime configuration, deployment manifests,
  scripts, dataset metadata, GPU inventory, final cluster state and InfiniBand
  counter snapshots/deltas. Counter data units were converted to bytes by ×4.

The generated 36.6 MiB dataset and model weights remain outside Git. Its seed,
tokenizer settings and SHA256 are recorded in the metadata and report.

CSV line endings and trailing spaces in log lines are normalized for Git;
request JSONL, metric values and recorded timing data are preserved.
