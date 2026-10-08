# 256K topology comparison

This experiment compares the same DeepSeek V4 Pro checkpoint on 16 H200 GPUs:
one TP8 prefill plus one TP8 decode worker, followed by two TP8 aggregated replicas.
At completion of this experiment, the deployment was aggregated at a 262,144-token
context window, with healthy workers using the original weights and bound PVCs.
The shared cluster subsequently switched to the [Nemotron 128K experiment](../nemotron-3-nano-128k-comparison/REPORT.md);
the DeepSeek weights and these results are preserved.

## Results — completed 30 September 2026

All **48/48 requests passed**. Every server prompt count matched the encoder,
and the notebook verified identical request bodies for all 24 paired turns.
Both runs saved all four worker-metric snapshots without collection errors.

| Metric | Disaggregated (1P + 1D) | Aggregated (2 replicas) |
| --- | ---: | ---: |
| Measured requests | 24 | 24 |
| Measured wall time | 782.50 s (13.04 min) | 141.45 s (2.36 min) |
| Actual input tokens | 6,144,780 | 6,144,780 |
| Actual output tokens | 2,214 | 2,413 |
| Output tokens/s | 2.83 | 17.06 |
| Median TTFT, all turns | 128.83 s | 0.80 s |
| Median TTFT, first turns | 126.49 s | 32.40 s |
| Median TTFT, follow-ups | 130.16 s | 0.65 s |
| Median TPOT, all turns | 12.67 ms | 13.11 ms |

The final matched measurements took **15.40 minutes combined**. Calibration,
cache-drain waits, warmups, dataset generation and worker restarts are recorded
separately and excluded from those times.

Aggregated completed this workload **5.53× faster** by wall time. All 16 aggregated
follow-ups reported 256,000 cached tokens. The disaggregated run did not report
cache hits, and its prefill logs show those long contexts being processed again.
The aggregated topology also has two nodes available for prefill, whereas 1P1D
has one. Thus this result includes scheduling and cache-retention differences;
it is not an isolated measurement of KV-transfer overhead or a universal topology
ranking. Decode TPOT was similar, with disaggregated slightly lower in this run.

### Saved artifacts

- Raw runs: `tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/20260930T223415Z-e8ee09b4/`
  (disaggregated) and `20260930T225241Z-a4a27eae/` (aggregated).
- Tracked summaries: [disaggregated CSV](validation-256k-disaggregated-summary.csv)
  and [aggregated CSV](validation-256k-aggregated-summary.csv).
- Notebook source: [deepseek_v4_pro_256k.ipynb](deepseek_v4_pro_256k.ipynb).
- Executed notebook and PNG/CSV charts: the result folder's `analysis/` directory.
- `study-records/`: exact commands, cache-clear acknowledgements, logs and exit status.
- `diagnostics/`: warmups, interrupted calibration and worker logs, excluded from
  the main comparison. `reproduction/`: model/runtime records, manifests, GPU
  inventory and benchmark scripts.

The complete [result archive](README.md),
including raw runs, diagnostics, charts and the executed notebook, is retained in
Git alongside the report, manifests and notebook source. Generated datasets remain
Git-ignored. An additional
copy of client artifacts remains on the existing `model-0` PVC under
`.benchmarks/longcontext`; the temporary CPU client pod is removed after export.

## Fixed protocol

- Model: `deepseek-ai/DeepSeek-V4-Pro-0813`, revision
  `72e1d3230f6c080a530b0a1d46f8eb4602340597`; same Dynamo/SGLang image, weights and PVCs.
- Context window: 262,144; actual prompt sizes: 256,000–256,074 tokens.
- Output budget: up to 256 tokens; temperature 0; thinking disabled.
- Client concurrency: 4 sessions, one in-flight turn per session.
- Per worker: TP8, four running requests, 4096-token prefill chunks, FP8 KV cache,
  Marlin MoE, 0.88 static memory fraction. Prefill-only worker has decode graphs
  disabled; decode and aggregated workers use decode graphs up to batch size 4.
- Dataset: eight three-turn sessions, 24 requests per topology. Both modes use
  the exact same file, ordering and request bodies.
- Client: dedicated CPU pod on node 0, using the frontend's ClusterIP. All GPU
  workers remain on the same two nodes, and the frontend is unchanged.
- Cache: the `clear_kv_blocks` endpoint must acknowledge success on both workers
  before the run. Within-session reuse is allowed but not guaranteed under load.
  `cache_state=mixed` describes this protocol; it is not a claim of cache hits.
- Warmup: a three-request 256K disaggregated pilot and two concurrent first-turn
  aggregated pilots (one on each replica), plus one short runner warmup. Pilot and interrupted calibration records are excluded from the final
  comparison. One measured run per topology targets 30 minutes total benchmarking.

## Dataset and ignored artifacts

The master generated dataset has 32 sessions / 96 requests and is about 91 MiB:
`datasets/generated/deepseek-v4-pro-chatbot-256k-32.jsonl`.
Its SHA256 is `66880756c3dcd5d55db6078a3b1a2442cd22388f1690310f11fd3c25f18f7033`.

The calibrated subset is the first eight complete sessions, about 23 MiB:
`datasets/generated/deepseek-v4-pro-chatbot-256k-8.jsonl`.
Its SHA256 is `815a787649a2d91ad90907aeda133ade0606795d622809959c5180679e3ac492`.
Both have metadata sidecars. `datasets/generated/` is explicitly ignored by Git.

A one-session pilot showed fast follow-up cache reuse. At concurrency 4, the
initial 32-session attempt instead reprocessed long contexts. It was interrupted
rather than exceeding the agreed time budget; its partial output is retained as
calibration evidence and excluded from reported rates. The subset was fixed
before either final measured run.

## Reproduction

The cached model is already present on both original PVCs. The disaggregated
alternative is `40-workers-disaggregated.yaml` with
`deployment-disaggregated.json`; the active aggregated configuration will be
`40-workers.yaml` with `deployment.json` after the comparison.

Run the benchmark client inside this namespace with the pinned runtime image,
4 CPU requested, 4Gi memory requested / 16Gi limit, and the repository's
`benchmarks/` package. The committed reproduction bundle records its exact Pod manifest.
It uses a `.benchmarks/longcontext` subdirectory on `model-0` for durable output.
Model weights are not copied to the client.

Place the selected dataset at `/bench/dataset.jsonl`, its sidecar alongside it,
and each topology's deployment record at
`/bench/{disaggregated,aggregated}-deployment.json`. Copy `clear_cache.py` and
`benchmark_256k.py` from this folder into `/bench`. The cache helper is specific
to this namespace and must run inside the cluster with Dynamo's Python runtime.
It clears idle KV caches only; it never modifies model weights.

After deploying and warming the chosen topology:

```bash
cd /bench
python3 benchmark_256k.py disaggregated
# After saving results, switching workers, waiting for readiness and warming:
python3 benchmark_256k.py aggregated
```

Each run snapshots both workers' Prometheus metrics and saves streaming events,
request metrics, aggregate summaries, dataset hashes and full deployment metadata.
Study records contain cache-reset acknowledgements, commands, status and timestamps.

Open `tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/deepseek_v4_pro_256k.ipynb` in the repository `.venv` kernel and
Run All. It reads `tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/`, verifies that paired
requests have identical bodies, then exports whole-run and first-turn/follow-up
comparison charts. Set `DEEPSEEK_256K_RESULTS` to read another result directory.

## Interpretation

This is a single-run, fixed-order comparison of a synthetic recorded workload.
It does not establish run-to-run variance, robust p99 latency, maximum capacity,
or answer quality. Actual output lengths can differ even with temperature zero;
compare request throughput and token counts alongside output-token throughput.
TTFT includes serving queue time. SGLang does not expose exact token-resolved ITL
through this API; TPOT is a per-response average, not a token-level tail metric.
