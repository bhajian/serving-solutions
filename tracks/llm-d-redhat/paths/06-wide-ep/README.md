# Path 06 · Wide expert parallelism

[Home](../../../../README.md) › [Tracks](../../../README.md) › [llm-d + Red Hat AI](../../README.md) › [Paths](../README.md) › 06 · Wide expert parallelism

**Status: planned.** Upstream: [guides/wide-ep](https://github.com/llm-d/llm-d/tree/release-0.10/guides/wide-ep).

## What it adds

Serves a large MoE model across nodes with data-parallel attention and expert parallelism (DP/EP), increasing KV capacity and decode throughput per GPU.

## Choose it when

Large MoE (DeepSeek-, Kimi-class) at high decode concurrency, ideally inside an NVLink domain; framework goals *throughput and cost* or decode-bound *output-optimized*. Usually paired with path 05 (wide EP on decode).

## Prerequisites

Multi-node scheduling (LeaderWorkerSet), GPUDirect RDMA, an engine build with EP kernels for the hardware.

## Deploy

Start from the upstream guide with the RHAIIS image and pull secret from
[install](../../install/README.md), and reuse the per-site weight handling of
[path 01](../01-optimized-baseline/README.md). Known blocker on Hopper with vLLM 0.26: MXFP4 Marlin MoE with expert parallelism hits an illegal memory access ([vllm#47769](https://github.com/vllm-project/vllm/issues/47769)), so DeepSeek V4 on H200 stays TP8 without EP until a fixed image ships.

## Test

Decode-heavy load at high concurrency; arms: TP8 replicas against DP/EP across nodes on the same GPUs. Metrics: output tokens/s per GPU, TPOT, KV capacity.
