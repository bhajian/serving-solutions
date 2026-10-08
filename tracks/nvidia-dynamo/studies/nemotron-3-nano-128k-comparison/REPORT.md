# Nemotron 3 Nano: 128K topology comparison

The experiment runs the same BF16 checkpoint on the same 16 H200 GPUs, first as
one TP8 prefill plus one TP8 decode worker, then as two TP8 aggregated replicas.
Both modes replay the same generated dataset three times. The measurement budget
is 30 minutes total, excluding download, startup, compilation and calibration.

## Results — completed 30 September 2026

All **576/576 measured requests passed**, with valid measurements and exact prompt-token
counts. Every one of the 96 session/turn request hashes matched across all six
runs. All 24 worker-metric snapshots were collected successfully.

| Metric | Disaggregated (1P + 1D) | Aggregated (2 replicas) |
| --- | ---: | ---: |
| Runs × requests | 3 × 96 | 3 × 96 |
| Mean run time (min–max) | 105.48 s (104.53–106.66) | 65.09 s (63.20–68.38) |
| Mean output tokens/s | 161.19 | 262.56 |
| Mean of run median TTFT | 2.503 s | 0.110 s |
| Mean of run median TPOT | 4.64 ms | 4.35 ms |
| First-turn median TTFT, pooled | 6.734 s | 2.814 s |
| Follow-up median TTFT, pooled | 0.257 s | 0.093 s |
| Follow-ups reporting cache hits | 192/192 | 190/192 |
| Actual input tokens, all repeats | 36,876,144 | 36,876,144 |
| Actual output tokens, all repeats | 51,006 | 51,204 |

Combined measured time was **8.53 minutes**, within the 30-minute budget.
Aggregated completed the same workload **1.62× faster** on mean wall time.
Disaggregated reported prefix-cache hits on all 192 follow-ups; aggregated
reported hits on 190 of 192. The DeepSeek 256K observation of missing
disaggregated follow-up hits did not recur here.
Aggregated can prefill on both nodes and avoids the inter-node state handoff;
this experiment does not separately isolate those contributions.

Across the disaggregated study interval, prefill transmitted **865.75 GiB** over
InfiniBand and decode received the same amount, about 108.22 GiB on each of the
eight ports. Counter snapshots include the short runner warmups. These counters
and the NIXL worker logs are saved as transfer evidence.

### Saved runs

| Mode | Run IDs |
| --- | --- |
| Disaggregated | `20260930T233220Z-9a685726`; `20260930T233410Z-7638e263`; `20260930T233557Z-df8c0fda` |
| Aggregated | `20260930T234109Z-195ac77a`; `20260930T234220Z-714521e9`; `20260930T234325Z-fffc898d` |

The [committed archive](./) contains raw
request records, metrics, cache-reset acknowledgements, pilots, worker logs and
reproduction files. Its `analysis/` directory contains the executed notebook,
PNG charts and exported CSV tables. The generated dataset remains Git-ignored.

### Endpoint and recovery validation

The cluster is left in aggregated mode at `http://<LOADBALANCER_IP>:8000/v1`.
Both workers are ready with zero restarts; both existing 1500Gi PVCs remain Bound.
The topology switch loaded the same local weights without another download.
Streaming and non-streaming public API checks passed in both modes. A separate
128,014-token retrieval check correctly returned a marker placed halfway through
the context, with an exact server/tokenizer prompt-count match. These checks are
excluded from performance measurements. This is a smoke check, not an answer-quality
benchmark. The temporary CPU client pod was removed after export; raw client
artifacts remain on its PVC subdirectory.

## Fixed protocol

- Model: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16`, revision
  `bf77c3174f68ad409e1c2aa60daeb46e32d1c606`.
- Dynamo 1.4.0 / SGLang 0.5.16, pinned runtime image digest in both deployment records.
- Context window: 131,072; actual prompts: 128,000–128,092 tokens.
- Output ceiling: 256 tokens; temperature 0; `enable_thinking=false`.
- Dataset: 32 sessions with three recorded turns each, 96 requests per run,
  three runs per mode, 288 requests per mode.
- Concurrency: four sessions, one in-flight turn per session.
- Both workers: TP8, four running requests, 4096-token prefill chunks, native
  KV dtype, FlashInfer attention, 0.88 static memory fraction, a 1,048,576-token
  KV pool limit, Mamba `no_buffer` radix strategy and overlap scheduling disabled.
- Disaggregation transfers attention KV and Mamba state through NIXL/UCX.
  The prefill worker disables CUDA graphs; decode and aggregated workers capture
  decode graphs up to batch size four. The runtime disables decode-side radix
  caching in PD mode; prefix reuse is handled by the prefill worker.
- In-cluster CPU client: four requested CPUs, 4Gi memory request / 16Gi limit,
  node 0, same frontend ClusterIP throughout.
- Both workers acknowledge cache reset before **each** measured run. Subsequent
  within-session prefix reuse is allowed. `cache_state=mixed` describes the
  protocol; actual reported cache hits are recorded separately.
- Pilot requests and runner warmups are excluded from the measured cohort.
  Topology order is fixed: all disaggregated repeats, then all aggregated repeats.

## Dataset

`datasets/generated/nemotron-3-nano-chatbot-128k-32.jsonl` contains 32 sessions,
96 recorded turns and 38,382,334 bytes. SHA256:
`0b3eaee6efc900ffce4bba9262fe90906e7b1468b56546c27c1ebd15d9e8bc39`.
Generated datasets remain Git-ignored; the metadata sidecar is saved with results.

Use the native tokenizer from the same pinned model revision. Unlike DeepSeek,
this checkpoint provides a Jinja chat template and does not need a Python encoder.

```bash
MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16
REV=bf77c3174f68ad409e1c2aa60daeb46e32d1c606
hf download "$MODEL" --revision "$REV" \
  --include 'tokenizer*' 'special_tokens*' 'chat_template*' 'config.json' \
  --local-dir build/nemotron-128k/tokenizer
.venv/bin/python -m benchmarks.generate_dataset \
  --workload chatbot --sessions 32 --input-tokens 128000 --output-tokens 256 \
  --max-model-len 131072 --seed 1282026 \
  --tokenizer build/nemotron-128k/tokenizer \
  --template-kwargs '{"enable_thinking":false}' \
  --out datasets/generated/nemotron-3-nano-chatbot-128k-32.jsonl
```

## Run inside the cluster

Deploy and warm disaggregated workers using the [site guide](../../sites/nebius-h200-2x8/nemotron-3-nano/README.md).
Create the CPU client and copy the package, dataset and mode records:

```bash
SITE=tracks/nvidia-dynamo/sites/nebius-h200-2x8/nemotron-3-nano
CLIENT=deepseek-v4-pro/benchmark-client
kubectl --context $KUBE_CONTEXT apply -f "$SITE/lab/as-measured/benchmark-client-128k/50-benchmark-client.yaml"
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro wait --for=condition=Ready pod/benchmark-client --timeout=5m
kubectl --context $KUBE_CONTEXT cp benchmarks "$CLIENT:/bench/" -c client
kubectl --context $KUBE_CONTEXT cp datasets/generated/nemotron-3-nano-chatbot-128k-32.jsonl "$CLIENT:/bench/dataset.jsonl" -c client
kubectl --context $KUBE_CONTEXT cp datasets/generated/nemotron-3-nano-chatbot-128k-32.jsonl.meta.json "$CLIENT:/bench/dataset.jsonl.meta.json" -c client
kubectl --context $KUBE_CONTEXT cp "$SITE/clear_cache.py" "$CLIENT:/bench/clear_cache.py" -c client
kubectl --context $KUBE_CONTEXT cp "$SITE/benchmark_128k.py" "$CLIENT:/bench/benchmark_128k.py" -c client
kubectl --context $KUBE_CONTEXT cp "$SITE/lab/as-measured/records/deployment-disaggregated.json" "$CLIENT:/bench/disaggregated-deployment.json" -c client
kubectl --context $KUBE_CONTEXT cp "$SITE/lab/as-measured/records/deployment.json" "$CLIENT:/bench/aggregated-deployment.json" -c client
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro exec benchmark-client -c client -- python3 -u benchmark_128k.py disaggregated
# Save disaggregated worker logs before replacing the pods.
kubectl --context $KUBE_CONTEXT apply -f "$SITE/lab/as-measured/workers-tp8-aggregated/40-workers.yaml"
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro rollout status deployment/worker-0 --timeout=20m
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro rollout status deployment/worker-1 --timeout=20m
# Warm both aggregated replicas with excluded pilot traffic before measuring.
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro exec benchmark-client -c client -- python3 -u benchmark_128k.py aggregated
```

The client persists output under `.benchmarks/nemotron128k` on the existing
`model-0` PVC. Export `/bench/results`, `/bench/study-records` and diagnostic pilot
outputs before deleting the client pod. Keep pilots outside the main results
root's immediate run directories so the collector excludes them.

Open [nemotron_3_nano_128k.ipynb](nemotron_3_nano_128k.ipynb) and
Run All in the repository `.venv` kernel. By default it reads
`tracks/nvidia-dynamo/studies/nemotron-3-nano-128k-comparison/`; set `NEMOTRON_128K_RESULTS` to analyze
another folder. The notebook checks request hashes across every run and exports
run-level comparisons, means/ranges and first-turn/follow-up distributions.

## Interpretation limits

This holds the original 16-GPU allocation fixed, rather than tuning GPU count for
this smaller model. Aggregated has two workers that can prefill; PD has one.
Cache reuse, transfer cost and scheduling all contribute to observed latency.
The three repeats show only a small sample of variation, and fixed topology order
leaves temporal effects unresolved. No claim about maximum capacity or robust
p99 latency follows from this workload.

The corpus is synthetic and conversations replay recorded histories. Answers are
not quality-scored. The token budget is a ceiling, so actual generated lengths
may differ. Output throughput is based on actual output tokens; cached input
throughput is not fresh-prefill throughput. TPOT is a response average because
token-resolved ITL is not available through this API.
