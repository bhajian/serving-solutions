# Path 02 · Precise prefix-cache routing

[Home](../../../../README.md) › [Tracks](../../../README.md) › [llm-d + Red Hat AI](../../README.md) › [Paths](../README.md) › 02 · Precise prefix-cache routing

**Status: planned.** Upstream: [guides/precise-prefix-cache-routing](https://github.com/llm-d/llm-d/tree/release-0.10/guides/precise-prefix-cache-routing).

## What it adds

Replaces path 01's approximate index with a global index of the real vLLM KV cache. Each vLLM pod publishes KV events (blocks stored and evicted) over ZMQ; the router scores pods on the blocks they actually hold, so evictions are seen immediately.

## Choose it when

Path 01 is in place and its prefix hit rate falls short of what the reuse in the profile predicts, typically because KV capacity is tight and the approximate index keeps routing to pods that already evicted the prefix (long contexts, many concurrent sessions).

## Prerequisites

Path 01. vLLM with `--kv-events-config` (ZMQ publisher, ports 5556/5559), a router block size equal to vLLM `--block-size`, and the router's tokenizer able to render chat prompts (`/v1/*/render`).

## Deploy

Start from the upstream guide with the RHAIIS image and pull secret from
[install](../../install/README.md), and reuse the per-site weight handling of
[path 01](../01-optimized-baseline/README.md). Open questions for the RHAIIS image: whether vLLM 0.26 serves the render endpoint the router tokenizer calls (upstream documents it with vLLM 0.30 and `--enable-scale-out`), and the block size for models with a hybrid KV layout such as DeepSeek V4 (block size 256 here, against 64 in the guide).

## Test

Same 256K multi-turn dataset as path 01, with concurrency raised until the aggregate working set exceeds per-replica KV capacity; arms: path 01 tuned against precise. Metrics: follow-up cache hit rate, follow-up TTFT, re-prefilled tokens.
