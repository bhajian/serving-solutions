# Nemotron 3 Nano: 8K input, 128K output topology comparison

This is the reverse of the [128K-input study](../nemotron-3-nano-128k-comparison/REPORT.md). Each request has a
medium-length prompt (8,000 tokens) and a very long, forced output (exactly 131,072
tokens). Both topologies run on the same 16 H200 GPUs as four TP4 workers. Each
mode uses as much concurrency as its KV pools allow:

- **Aggregated:** four TP4 replicas with 512 requests in flight (128 per worker).
- **Disaggregated:** one TP4 prefill worker and three TP4 decode workers, with 384
  requests in flight (128 per decode worker).

## Results — completed 1 October 2026

All **2,688 measured requests passed** (3 × 512 aggregated, 3 × 384 disaggregated).
Every completion contained exactly 131,072 tokens and every prompt exactly 8,000.
The two modes generated 352,321,536 output tokens between them.

| Metric (mean of 3 runs, min–max) | Disaggregated (1P + 3D) | Aggregated (4 replicas) |
| --- | ---: | ---: |
| Requests in flight | 384 | 512 |
| Run time | 32.45 min (32.36–32.61) | 32.25 min (32.12–32.40) |
| **Output tokens/s, whole run** | **25,852** (25,725–25,921) | **34,677** (34,525–34,817) |
| Output tokens/s per GPU | 1,616 | 2,167 |
| Steady-state decode tokens/s | 27,185 | 35,288 |
| TTFT p50 / p99 | 36.5 s / 72.6 s | 11.0 s / 22.6 s |
| TPOT p50 / p99 | 14.15 / 14.35 ms | 14.51 / 14.75 ms |
| ITL p50 / p90 / p99 (client) | 13.13 / 18.56 / 20.70 ms | 13.17 / 18.71 / 20.95 ms |
| ITL p50 / p99 (server histogram) | 13.07 / 19.96 ms | 13.17 / 20.36 ms |
| ITL p99.9 | 499 ms | 510 ms |
| **Worst ITL** | **1.14 s** (1.04–1.24) | **40.4 s** (40.2–40.9) |
| Gaps over 1 s per request | 0.6 | 2.7 |
| Time in gaps over 100 ms per request | 109 s | 159 s |

**Throughput:** aggregated produced **1.34× more output tokens per second** on the
same 16 GPUs. This workload is almost entirely decode: prefill is 8,000 of
139,072 tokens per request. Disaggregation reserves a quarter of the GPUs for
prefill, and that worker is idle for most of each 32-minute run. The 34% difference
corresponds to one fewer decode worker (three instead of four). Per-worker decode
speed is similar; TPOT is 2.5% lower in disaggregated mode because each decode
worker never runs prefill.

**Time to first token:** disaggregated TTFT is about 3.3× higher because a
synchronized wave queues 384 × 8,000 = 3.07M prompt tokens on **one** TP4 prefill
worker. In aggregated mode, four workers each prefill 128 prompts. This result
comes from the burst arrival pattern. It is not a fixed cost of transfer: in the
warmed 6-request smoke test, disaggregated TTFT was 0.2–1.0 s.

**Inter-token latency:** the medians and p99s are nearly identical. ITL rises with
context in both modes, from about 9 ms at the start of the output to about 20 ms
at 128K (see the ITL-by-position chart). The difference is in the tail:

- **Prefill stalls decode in aggregated mode.** While a worker prefills prompts that
  arrived later, its running streams pause; individual gaps reached 13 s during the
  first 30 s of each run. Disaggregated decode workers never prefill, so this does
  not occur.
- **Aggregated workers also freeze for about 37 s at the end of each run.** When a
  worker's 128 streams are within a few hundred tokens of completion, all of them
  stop together for about 37 s. This is the 40 s worst-case ITL. It does not occur
  on disaggregated decode workers, where SGLang disables the radix cache. That
  suggests (but does not prove) a cost of inserting 128 finished sequences of
  about 139K tokens each into the radix tree at once.
- **Both modes show a periodic ~0.5 s output pause.** Each worker pauses all of its
  streams for about 0.5 s about every 10 s. That is about 190 pauses per request in
  both modes, and it sets p99.9 to about 500 ms. The server histogram records the same
  pauses. They happen after the scheduler, not on the GPU: decode steps continue
  every ~13–15 ms throughout. Each `dynamo.sglang` main process uses about 110%
  CPU. See [diagnostics](#diagnostics-after-the-measured-runs).

ITL token coverage was ≥ 99.98%: almost every token arrived in its own stream
event. When chunks merged, only 2–10 tokens out of 131,072 were affected.

### Saved runs

| Mode | Router | Run IDs |
| --- | --- | --- |
| Aggregated | KV (balanced 128/128/128/128) | `20261001T140242Z-8fafdc7b`; `20261001T143536Z-e3b85d7d` |
| Aggregated | round-robin | `20261001T160754Z-da1a442e` |
| Disaggregated | round-robin | `20261001T165156Z-d6a807a3`; `20261001T172431Z-9bde84bd`; `20261001T175720Z-09b15755` |

The [archive](./) contains the request
CSVs and row JSONL, summaries, metadata, the eight worker-metric snapshots per run,
ITL-by-position tables, throughput timelines, pilots, study records and the executed
notebook. The per-token interval binaries (about 268 MB per aggregated run) remain on
the client PVC under `.benchmarks/nemotron8k128k`. `benchmarks.long_decode --reanalyze`
regenerates summaries from them.

### Excluded runs

Both excluded runs are retained under `excluded-runs/` with the reason for exclusion:

1. **`queued-at-cap-128`:** the first aggregated attempt, with each worker capped at 128
   requests. The router assigned 129–130 requests to some workers, so a few requests
   waited until the end of the wave. The run was stopped after a few minutes, and the
   cap was raised to 136 (the KV pools fit 140 complete requests).
2. **`router-imbalance`:** the third aggregated run with the KV router, which sent 152
   requests to one worker and 120 to each of the others. Sixteen requests queued for
   37 minutes, and the run reported 21,968 tokens/s. That measured placement, not
   decode capacity. Prompts are unique, so the KV router has no cache reuse to exploit.
   The frontend was then switched to round-robin (`31-frontend-round-robin.yaml`) for
   the replacement aggregated run and for all disaggregated runs. The two KV-router
   runs that are kept had exactly 128 requests per worker and match the round-robin
   run within 0.9% throughput.

A second copy of the driver started 2 minutes after aggregated run 1 began. It tried to
clear caches, the workers refused because requests were active, and it exited. It did,
however, overwrite that run's cache-clear log. The worker logs show all four flushes
at 14:02:42 UTC, before the run, and are saved as
`aggregated-c512-o131072-measured-1-flush-evidence-from-worker-logs.log`. The driver now
holds an exclusive lock.

## Concurrency pilots

Pilots used 8,192 forced output tokens (contexts under 16K), so their absolute TPOT is lower
than in the full runs. Throughput increased up to the KV limit in both modes, so the full runs
use the maximum.

| Mode | In flight | Output tok/s | Steady tok/s | TTFT p50 | TPOT p50 | ITL max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Aggregated | 64 / 128 / 256 / 512 | 12,640 / 20,527 / 31,473 / 31,034 | 13,341 / 22,062 / 35,100 / — | 1.4 / 2.7 / 5.5 / 11.6 s | 4.81 / 5.82 / 7.31 / 11.04 ms | 2.9 / 5.2 / 11.0 / 22.7 s |
| Disaggregated | 48 / 96 / 192 / 384 | 8,551 / 13,164 / 18,515 / 23,906 | 10,332 / 17,854 / 29,366 / — | 4.3 / 8.7 / 17.7 / 36.2 s | 4.66 / 5.42 / 6.63 / 8.58 ms | 0.06 / 0.01 / 0.7 / 0.6 s |

In the 512 pilot, the prefill ramp took about 100 s of an 8,192-token run, so whole-run
throughput did not increase. Over a full 128K run the ramp is negligible, and decode at 512
was faster (46K tokens/s at batch 512 versus 35K at 256).

## Diagnostics after the measured runs

These checks ran after all six measured runs, on the disaggregated deployment. Their
outputs are in `diagnostics/` in the archive. None of them changes a measured result.

**The ~0.5 s periodic pause is Python garbage collection.** Decode `worker-1` was restarted
with `--gc-warning-threshold-secs 0.1` and a 384-request wave (24,576 output tokens) was
sent. SGLang logged 26 **generation-2 collections** in about 300 s: one every ~11.5 s,
each taking 0.34–0.45 s (median 0.38 s) and scanning about 890K objects
(`decode-worker-gc-warnings.log`). This matches the client and server ITL pauses in
both rate and size. Decode-step logging continued during the collections, so the GPU
scheduler was not the process that stopped. The pause is on the output path, consistent
with the CPU-saturated `dynamo.sglang` main process. SGLang's warning recommends calling
its `freeze_gc` API after warmup. Testing that, or raising the GC thresholds, is the
obvious next step. It would affect both topologies equally and mainly the ITL p99.9.

**The prefill worker's host memory swings by more than 100 GiB, and it was OOM-killed once.**
`worker-0` (prefill) was OOM-killed at 18:32:37 UTC, 2 minutes 43 seconds after the last
measured run finished, while a 6-request warmup was running. The container limit is 384 GiB
(`prefill-oom-kill.json`). After a restart, its anonymous memory was sampled every ~13 s
during a 384-request wave (`prefill-host-memory-during-384-wave.csv`):

- 14 GiB idle → 84 GiB during NIXL connection setup with the first requests.
- During the prefill and transfer burst, memory swung between 104 and **308 GiB**.
- It then stayed at 201 GiB for the rest of the decode phase.

Flushing the KV cache did not release it. Replaying already-cached prompts barely
changed it (+0.13 GiB for 96 requests); 96 new prompts added 108 GiB. Decode workers
stayed at 11–13 GiB. A 384-request burst therefore leaves the prefill pod with only about
75 GiB of headroom below its limit. The source of these host allocations, probably
transfer staging buffers in the PD path, was not identified. Before using this layout
in production, raise the prefill memory limit or limit the number of concurrent
prefills in flight.

**Discovery can lose the prefill worker after restarts.** After the diagnostic decode worker
was restored, the frontend's etcd watch failed ("channel closed"). The frontend dropped every
worker and returned 503, although all four pods were Ready. Restarting the frontend
re-registered the decode workers, but the prefill worker's registration was gone ("Prefill
router deactivated"). Restarting `worker-0` then restored service. If the endpoint returns 503
"not ready" in disaggregated mode, check the frontend log for prefill router activation before
debugging the engines.

## Fixed protocol

- Model `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16`, revision
  `bf77c3174f68ad409e1c2aa60daeb46e32d1c606`; Dynamo 1.4.0 / SGLang 0.5.16 with the
  same pinned image digest as the 128K study.
- Context 262,144 (the model maximum). Prompts exactly 8,000 tokens. Output forced to
  exactly 131,072 tokens with `ignore_eos: true`. Temperature 0, `enable_thinking=false`.
- Dataset: 512 single-turn sessions with unique prefixes. The first 512 (aggregated) or
  384 (disaggregated) sessions are used, so every disaggregated prompt also appears in
  the aggregated runs. Request hashes match across runs.
- One closed-loop wave per run: every request is sent at time zero, and the run ends
  when the last stream finishes.
- Workers: TP4 on four GPUs, two workers per node, all with identical engine flags apart
  from the PD role. `--max-running-requests 136` and CUDA graphs up to batch 136. The KV
  pool is sized automatically (19.6M tokens per worker). 4,096-token prefill chunks,
  0.88 static memory fraction, FlashInfer attention, Mamba `no_buffer` radix cache,
  overlap scheduling disabled, native KV dtype, BF16 weights. The prefill worker
  disables CUDA graphs. Disaggregation uses NIXL over UCX on the eight InfiniBand
  interfaces. Every disaggregated request was prefilled on the prefill worker and
  decoded on a different worker, 128 per decode worker.
- Frontend: Dynamo frontend with round-robin routing; the first two aggregated runs used
  the KV router (see above).
- Caches on all four workers are flushed, with acknowledgement, before every run.
- Client: CPU pod on node 0 with 20 CPUs and 16 parser processes sharing one
  CLOCK_MONOTONIC start. It uses the same frontend ClusterIP throughout.
- Order: aggregated pilots and runs, then disaggregated pilots and runs.

## Metrics

| Metric | Definition |
| --- | --- |
| Output tokens/s | Valid output tokens divided by wall time from the shared start to the last completion. |
| Steady decode tokens/s | Tokens produced after every stream has its first token and before any stream finishes, divided by that window's length. |
| TTFT | Request start to the first stream event. It includes queueing in the frontend and prefill worker. |
| TPOT | (last event − first event) / (completion tokens − 1), per request. |
| ITL (client) | Interval between successive stream events carrying a delta. Empty-text deltas count too; after end-of-sequence most tokens detokenize to empty text. Percentiles pool every interval of every valid request. |
| ITL coverage | Stream events / completion tokens. A value of 1 means one event per token. |
| ITL (server) | Delta of SGLang's `inter_token_latency_seconds` histogram over the run, summed across workers, with 1 ms buckets up to 40 ms. |
| Gaps over N ms | Count of intervals above 50, 100 or 1,000 ms, and total time spent in intervals above 100 ms, per request. |

## Reproduce

```bash
SITE=tracks/nvidia-dynamo/sites/nebius-h200-2x8/nemotron-3-nano
MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16
.venv/bin/python -m benchmarks.generate_dataset --workload chatbot --sessions 512 --turns 1 \
  --input-tokens 8000 --output-tokens 131072 --max-model-len 262144 --seed 8128026 \
  --tokenizer build/nemotron-128k/tokenizer --template-kwargs '{"enable_thinking":false}' \
  --out datasets/generated/nemotron-3-nano-chatbot-8k-512.jsonl
.venv/bin/python $SITE/render_tp4.py           # writes both TP4 worker manifests
kubectl --context $KUBE_CONTEXT apply -f $SITE/lab/as-measured/frontend-round-robin/31-frontend-round-robin.yaml
kubectl --context $KUBE_CONTEXT apply -f $SITE/lab/as-measured/workers-tp4-aggregated/40-workers-tp4.yaml   # or 40-workers-tp4-disaggregated.yaml
kubectl --context $KUBE_CONTEXT apply -f $SITE/lab/as-measured/benchmark-client-8k-128k/51-benchmark-client-long-decode.yaml
CL=deepseek-v4-pro/benchmark-client
kubectl --context $KUBE_CONTEXT cp benchmarks $CL:/bench/ -c client
kubectl --context $KUBE_CONTEXT cp datasets/generated/nemotron-3-nano-chatbot-8k-512.jsonl $CL:/bench/dataset.jsonl -c client
kubectl --context $KUBE_CONTEXT cp datasets/generated/nemotron-3-nano-chatbot-8k-512.jsonl.meta.json $CL:/bench/dataset.jsonl.meta.json -c client
for f in clear_cache.py benchmark_8k_128k.py; do kubectl --context $KUBE_CONTEXT cp $SITE/$f $CL:/bench/$f -c client; done
kubectl --context $KUBE_CONTEXT cp $SITE/lab/as-measured/records/deployment-tp4.json $CL:/bench/aggregated-deployment.json -c client
kubectl --context $KUBE_CONTEXT cp $SITE/lab/as-measured/records/deployment-tp4-disaggregated.json $CL:/bench/disaggregated-deployment.json -c client
# After a restart, send a short warmup first: disaggregated NIXL setup takes about 60 s on the first requests.
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro exec benchmark-client -c client -- \
  python3 -u benchmark_8k_128k.py aggregated --concurrency 512 --repetitions 3
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro exec benchmark-client -c client -- \
  python3 -u benchmark_8k_128k.py disaggregated --concurrency 384 --repetitions 3
```

Each run takes about 33 minutes. Run the driver detached (`nohup setsid … &`) so that a
dropped `kubectl exec` session does not stop it. Pilots: add `--output-tokens 8192
--repetitions 1 --label pilot --results pilots`. Analysis:
[nemotron_3_nano_8k_128k.ipynb](nemotron_3_nano_8k_128k.ipynb). It reads
the archive by default; set `NEMOTRON_8K_128K_RESULTS` to read another folder. The
notebook is generated by `tools/build_8k_128k_notebook.py`.

To return to the 128K-study topology, delete `worker-2` and `worker-3`, then apply
`30-frontend.yaml` and `40-workers.yaml` (or `40-workers-disaggregated.yaml`).

## Interpretation limits

- The GPU split is fixed at four TP4 workers. A smaller prefill worker (TP1 or TP2) with
  more decode workers would narrow the throughput gap; that configuration was not measured.
- A synchronized wave produces the largest possible prefill burst and an abrupt end.
  With staggered arrivals, prefills would be spread through decode, raising aggregated
  stall frequency and lowering disaggregated TTFT. This study does not measure open-loop
  arrival rates.
- Concurrency differs by design (128 per decode-capable worker). Per-request latency
  should be compared at that per-worker load, not at equal client concurrency.
- Output after the model's end-of-sequence token is not meaningful text. Compute per
  token is unchanged, but output quality is not assessed.
- Overlap scheduling is disabled in both modes, as in the 128K study. This compares the
  same settings in two topologies; neither topology was individually tuned.
- Three runs per mode give only a small sample. Topology order was fixed.
