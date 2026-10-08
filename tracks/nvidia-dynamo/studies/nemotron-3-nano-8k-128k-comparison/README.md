# Nemotron 3 Nano 8K-in / 128K-out comparison — 1 October 2026

> Raw evidence (streaming JSONL, worker-metric snapshots, logs, charts and the
> executed notebook) is in this study's release archive; see [ARCHIVE.md](../ARCHIVE.md).
> `ARCHIVE-MANIFEST.sha256` lists every archived file with its checksum.

Six measured runs on the same 16 H200 GPUs and pinned BF16 checkpoint, configured as
four TP4 workers. Three aggregated runs (4 replicas, 512 requests in flight) were
followed by three disaggregated runs (1 prefill + 3 decode, 384 in flight). Every
request has an 8,000-token prompt and exactly 131,072 output tokens (`ignore_eos`).

**2,688/2,688 requests passed.** Aggregated averaged **34,677 output tokens/s**, against
**25,852** for disaggregated (1.34×). Median TPOT and ITL were nearly identical (about 14 ms
and 13 ms). Disaggregated TTFT was 3.3× higher because all prompts queue on one prefill
worker. Disaggregation removed aggregated's prefill and end-of-run decode stalls: the
worst ITL fell from 40.4 s to 1.1 s. Both modes show a ~0.4 s generation-2 Python GC
pause about every 10 s per worker, which sets ITL p99.9 to about 500 ms.

See the [full report and protocol](REPORT.md)
for settings, interpretation, excluded runs, diagnostics and reproduction steps. The earlier
[128K-input / 256-output study](../nemotron-3-nano-128k-comparison/) is unchanged; the
notebook places the two studies side by side.

- Timestamped run directories: `requests.csv`, per-process `rows-*.jsonl`, `summary.csv/json`,
  `metadata.json` (including the full deployment record), eight before/after worker-metric
  snapshots, `itl_by_position.csv` (1,024-token bins) and `throughput_timeline.csv` (10 s windows).
- `analysis/`: executed notebook (`analysis/nemotron_3_nano_8k_128k.executed.ipynb`, archived), PNG
  charts and exported CSV tables. The [source notebook](nemotron_3_nano_8k_128k.ipynb)
  reads this folder without access to the cluster.
- `pilots/`: concurrency pilots (8,192 output tokens) and smoke runs; not part of the comparison.
- `study-records/`: driver commands, cache-flush acknowledgements, logs and completion status.
- `excluded-runs/`: the aborted first attempt (worker cap 128) and the KV-router imbalance run,
  each kept with its records.
- `diagnostics/`: GC-pause warnings, prefill host-memory samples, the OOM record and diagnostic runs.

The per-token interval binaries (`intervals-*.f32`, about 268 MB per aggregated run) and the
generated dataset stay outside Git. The binaries are on the client PVC under
`.benchmarks/nemotron8k128k/`. Worker and frontend logs are in `build/nemotron-8k-128k/`.
