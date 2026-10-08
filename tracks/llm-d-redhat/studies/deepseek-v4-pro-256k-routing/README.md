# DeepSeek V4 Pro 256K: cache-unaware vs prefix-aware routing

[Home](../../../../README.md) › [Tracks](../../../README.md) › [llm-d + Red Hat AI](../../README.md) › [Studies](../README.md) › 256K routing

**Status: running** (started 2026-10-08). Path: [01 · Optimized baseline](../../paths/01-optimized-baseline/README.md).
Profile: [deepseek-v4-pro-256k-multiturn.yaml](../../../../framework/1-intake/examples/deepseek-v4-pro-256k-multiturn.yaml).

## Question

On four identical TP8 replicas, how much does prefix-aware scheduling in the llm-d router
save on multi-turn sessions over 256K-token contexts, compared with cache-unaware placement?
Turns 2 and 3 of each session extend turn 1's prompt; they are cheap only on the replica
that already holds that prefix.

## Fixed protocol

| Item | Value |
| --- | --- |
| Model | `deepseek-ai/DeepSeek-V4-Pro-0813` @ `72e1d3230f6c080a530b0a1d46f8eb4602340597` |
| Engine | RHAIIS `3.6.0-fast.1` (vLLM `0.26.0+rhaiv.8`), pinned by digest; TP8, FP8 KV, block size 256, prefix caching on, 262,144-token window |
| Replicas | 4, one per node, 32 H200 GPUs; each with its own copy of the weights (verified byte count and revision) |
| Router | llm-d router v0.11.0 standalone (EPP + Envoy); the same `utilization-detector` thresholds in every arm |
| Dataset | `datasets/generated/deepseek-v4-pro-chatbot-256k-32.jsonl`, SHA256 `66880756c3dc…7033`: 32 sessions × 3 turns, 256,000–256,074 prompt tokens, the same file as the Dynamo 256K study |
| Requests | Streaming, temperature 0, up to 256 output tokens, thinking disabled |
| Client | In-cluster pod, through the router's ClusterIP Service; closed loop |
| Before each arm | Apply the arm's scheduler, restart the router (clears its prefix index), wait for all four endpoints, reset every replica's prefix cache (`POST /reset_prefix_cache`, acknowledgements saved) |

## Arms

| Arm | Scheduler | Router values |
| --- | --- | --- |
| `random` | `random-picker` only: cache-unaware (the router has no strict round-robin picker) | [arm-random.yaml](../../paths/01-optimized-baseline/deepseek-v4-pro-h200/router/arm-random.yaml) |
| `optimized-baseline` | The guide's plugins with their shipped defaults | [arm-optimized-baseline.yaml](../../paths/01-optimized-baseline/deepseek-v4-pro-h200/router/arm-optimized-baseline.yaml) |
| `optimized-baseline-tuned` | Same plugins: whole-prompt matching, `peakPrefillThroughput` measured at 256K, load threshold from measured KV capacity | Written after calibration |

## Metrics

TTFT by turn (first vs follow-up), `cached_tokens` per request, per-replica request count and
prefix-cache hit rate (vLLM metrics before and after), router decisions
(`llm_d_epp_prefix_cache_affinity_filter_decisions_total`), wall time and throughput.

## Run

```bash
cd tracks/llm-d-redhat/studies/deepseek-v4-pro-256k-routing
kubectl --context "$KUBE_CONTEXT" -n llm-d apply -f client.yaml
# copy benchmarks/ and the dataset into the client pod, then per arm:
./run_arm.sh random r1
./run_arm.sh optimized-baseline b1
```

`calibrate.py` (run in the client pod) measures cold 256K prefill throughput on one replica,
bypassing the router; its output sets the tuned arm's parameters.
