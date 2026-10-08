# Path 01 · Optimized baseline

[Home](../../../../README.md) › [Tracks](../../../README.md) › [llm-d + Red Hat AI](../../README.md) › [Paths](../README.md) › 01 · Optimized baseline

**Status: deployed** on 4 × 8 H200 (Nebius) with DeepSeek V4 Pro 0813;
[256K routing study](../../studies/deepseek-v4-pro-256k-routing/README.md) running.
Upstream: [guides/optimized-baseline](https://github.com/llm-d/llm-d/tree/release-0.10/guides/optimized-baseline).

## What it adds

Aggregated vLLM replicas behind the llm-d router, which scores pods by **approximate prefix
cache affinity** (it hashes each prompt in blocks and remembers where it sent them) and by
**in-flight token load**. Requests that share a prefix go back to the replica that holds it,
unless that replica is so busy that recomputing elsewhere would be faster.

| Scheduler plugin | Role |
| --- | --- |
| `approx-prefix-cache-producer` | Hashes prompt blocks; per-pod LRU index of what each pod should have cached |
| `inflight-load-producer` | Tracks uncached tokens in flight per pod |
| `prefix-cache-affinity-filter` | Keeps pods whose prefix match ≥ 0.80, unless the estimated TTFT penalty exceeds `maxTTFTPenaltyMs` |
| `token-load-scorer` | Prefers the least-loaded remaining pod |

## Choose it when

Framework D1 picks *aggregated + prefix-aware routing*: more than one replica and any prefix
reuse (multi-turn chat, agents, shared system prompts, repeated documents). It is the starting
point for every other path; paths 02–04 refine it and 05–08 build on it.

## Prerequisites

[Install](../../install/README.md) steps 1–4. Per replica: enough GPUs for the weights plus KV
([sizing](../../../../framework/3-size/README.md)) and a weight volume the replica can mount.

## Deploy

Instance: [deepseek-v4-pro-h200/](deepseek-v4-pro-h200/README.md), a StatefulSet with one TP8
replica per node and one RWO weight disk per replica, plus router values with one file per
scheduler arm.

## Test

The [256K routing study](../../studies/deepseek-v4-pro-256k-routing/README.md) replays 32
three-turn sessions over unique 256K-token contexts through the router, under three schedulers:
cache-unaware random, this path's configuration as shipped, and the same tuned for 256K
prompts. It reports TTFT by turn, cached tokens per request, per-replica hit rate and the
router's own decisions.

## Known limits (router v0.11.0)

- Defaults are tuned for short prompts: only the first 131,072 tokens are hashed, and
  `peakPrefillThroughput` is calibrated for Qwen3-32B on H100. Long-context deployments
  should match the whole prompt and calibrate prefill throughput at their real ISL.
- The router counts tokens as prompt bytes ÷ 4, not model tokens.
- There is no strict round-robin picker; `random-picker` is the cache-unaware baseline.
