# Path 04 · Tiered prefix cache

[Home](../../../../README.md) › [Tracks](../../../README.md) › [llm-d + Red Hat AI](../../README.md) › [Paths](../README.md) › 04 · Tiered prefix cache

**Status: planned.** Upstream: [guides/tiered-prefix-cache](https://github.com/llm-d/llm-d/tree/release-0.10/guides/tiered-prefix-cache).

## What it adds

Offloads KV blocks beyond GPU memory to CPU memory and local disk, so the reusable working set can exceed HBM. Returning sessions reload instead of recomputing.

## Choose it when

The profile's reuse working set (active sessions × reusable context) exceeds the aggregate KV of the replicas that hold it ([sizing step 7](../../../../framework/3-size/README.md#steps)): multi-turn chat with idle sessions, agents, repeated long documents.

## Prerequisites

Path 01; host memory headroom per node (the H200 nodes have 1.6 TB, of which the weights page cache can use about 900 GB during load) and, for a disk tier, fast local NVMe.

## Deploy

Start from the upstream guide with the RHAIIS image and pull secret from
[install](../../install/README.md), and reuse the per-site weight handling of
[path 01](../01-optimized-baseline/README.md). Pending: which offload connector the RHAIIS build ships (vLLM native offloading or LMCache), and its interaction with DeepSeek V4's compressed KV format.

## Test

256K multi-turn sessions with think time between turns, so sessions go idle and are evicted from HBM; arms: path 01 against tiered. Metrics: follow-up TTFT and hit rate by tier.
