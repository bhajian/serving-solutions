# Raw result archives

[Home](../../../README.md) › [Tracks](../../README.md) › [NVIDIA Dynamo](../README.md) › [Studies](README.md) › Archive

The tree keeps what the analysis notebooks read: per-request CSVs, summary and
metadata JSON, ITL/timeline tables and the study READMEs. Raw evidence is published
as release assets, one tarball per study:

| Archive | Contents | SHA256 |
| --- | --- | --- |
| `deepseek-v4-pro-256k-comparison.tar.gz` | 36 files: streaming JSONL, Prometheus snapshots, logs, charts, executed notebook | `609207d790a14c8919b9bcd0d46bc6f41fe07815c410a33c6eaa46652a515b9f` |
| `nemotron-3-nano-128k-comparison.tar.gz` | 60 files: as above, plus IB counters and pilot logs | `97dc16b24488424c5a222b3620e4b5608f94d4cb852b544887e2dce95a5363b4` |
| `nemotron-3-nano-8k-128k-comparison.tar.gz` | 533 files: row JSONL, 8 metric snapshots per run, charts, executed notebook, diagnostics | `03c5ebacdf5f9bd05d0868c68d2af5831511dab2e0d56495ed39a1cc5fc3d155` |

Every study folder holds `ARCHIVE-MANIFEST.sha256` (one line per archived file), so
an archive can be checked file by file after download:

```bash
gh release download results-archive-2026-10-01 -D build/archives   # repository release assets
python tools/archive_results.py restore --from build/archives       # extracts and verifies checksums
```

Maintainers create the archives with `python tools/archive_results.py pack` and
publish them with
`gh release create results-archive-2026-10-01 build/archives/*.tar.gz`.
Per-token interval binaries (`intervals-*.f32`, about 268 MB per aggregated 8K/128K
run) were never committed; they remain on the benchmark client PVC.

These files were committed directly in earlier history. They are still reachable
in old commits; removing them from the main tree keeps clones and reviews small.
