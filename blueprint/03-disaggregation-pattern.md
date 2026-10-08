# 03 · The disaggregation pattern

[Home](../README.md) › [Blueprint](README.md) › 03 · Disaggregation pattern

**Executive summary.** Disaggregation runs prefill and decode on separate pools so each can be batched, parallelized and scaled for its own phase, at the cost of one KV transfer per request. On the H200 site it removed prefill-induced decode stalls but was slower overall at fixed P:D ratios ([chapter 12](12-results-and-reconciliation.md)). Whether it wins depends on the workload, the SLO, P:D tunability and the fabric.

| What you get from this repository | What you still own |
| --- | --- |
| Aggregated and disaggregated graphs with NIXL/UCX transfer settings, and three measured comparisons | Choosing the P:D ratio for your traffic |

Disaggregated serving splits each request's two phases, **prefill** and **decode**, onto separate GPU pools that scale independently. The split adds one KV handoff per request, so the fabric becomes part of the architecture.

## Two phases, two resource profiles

| | Prefill | Decode |
|---|---|---|
| Work | Process every prompt token in parallel | Generate one token per sequence per step |
| Bottleneck | GPU **compute** (FLOPs) | GPU **memory bandwidth** (reading weights and KV every step) |
| Latency it drives | **TTFT**: time to first token | **ITL / TPOT**: time between tokens |
| Grows with | Input length | Output length × concurrent sequences |
| Ideal batch | A few long prompts | Many sequences at once |
| Output | The **KV cache** for the prompt | Tokens, appending to the KV cache |

## Aggregated vs disaggregated

![Aggregated vs disaggregated serving](../assets/diagrams/png/agg-vs-disagg.png)

In **aggregated** serving, every replica runs both phases in one batch on one set of GPUs. When a long prompt arrives, its prefill occupies the GPUs and every in-flight decode waits. Users mid-stream see a stall. Chunked prefill softens this but cannot remove it.

In **disaggregated** serving, prefill workers compute the KV cache and hand it to decode workers over the GPU fabric. Decode GPUs only decode, so prefill never stalls their streams: on the H200 site the worst inter-token gap was 1.1 s disaggregated against 40.4 s aggregated ([chapter 12](12-results-and-reconciliation.md)). Throughput and TTFT then depend on whether the P:D ratio fits the traffic. Each pool gets the batch size, memory split and parallelism that suit its phase, and each pool scales with its own traffic.

## What changes when the phases are split

| Concern | Aggregated | Disaggregated |
|---|---|---|
| Scaling unit | One replica runs both phases | Prefill and decode pools scale separately (Dynamo Planner) |
| Batch composition | Prefill chunks share a batch with decode steps | Each pool batches only its own phase |
| Parallelism | One layout for both phases | Per phase: small TP (+EP) for prefill, wide EP + DP attention for decode |
| Routing | KV-aware router picks one worker | Router picks a prefill and a decode worker |
| Per-request cost | None beyond compute | One transfer of the prompt's KV cache (and Mamba state for hybrid models) |
| Contract between workers | None | Prefill and decode must match model revision, TP layout, block size and KV dtype |
| Failure modes | A worker failure loses its requests | Also: transfer failures, bootstrap timeouts, a missing prefill pool |

The transfer is the defining cost. A prompt's KV cache is gigabytes, not kilobytes, so the
design only works on fabrics built for it: GPUDirect RDMA over InfiniBand or RoCE, or
NVLink inside a rack. The Nemotron 128K study moved 865.75 GiB over InfiniBand across its
three disaggregated runs, warmups included ([chapter 12](12-results-and-reconciliation.md)).

## Life of a request

1. The frontend tokenizes the request, applies the chat template and picks a prefill and a decode worker by KV overlap and load.
2. The prefill worker computes the KV cache for the whole prompt.
3. It returns the first token and handles for the KV blocks.
4. The frontend sends the decode request with those handles.
5. The decode worker **reads the KV blocks directly from prefill GPU memory** with RDMA (vLLM + NIXL). With SGLang, decode handshakes with prefill's bootstrap server and prefill pushes the KV.
6. The decode worker streams tokens back through the frontend.

In llm-d, a routing sidecar on the decode pod drives steps 2 to 4 instead of the frontend ([chapter 04](04-orchestration-layer.md)).

## The cost of the extra edge

Disaggregation adds one transfer per request. Whether it pays off depends on the fabric.

```text
KV bytes per token (attention layers) = 2 × layers × KV heads × head dim × bytes per element
Example, dense 70B-class, GQA 8 heads, head dim 128, 80 layers, FP8:
  2 × 80 × 8 × 128 × 1 B ≈ 160 KiB per token  →  a 32,000-token prompt ≈ 5 GiB
```

| Path | Approximate bandwidth | Time for 5 GiB |
|---|---|---|
| 8 × 800 Gb/s rails, GPUDirect RDMA | ~800 GB/s aggregate | ~7 ms |
| 1 × 800 Gb/s rail | ~100 GB/s | ~55 ms |
| Rack-scale NVLink (per GPU) | ~1.8 TB/s (Blackwell) | a few ms |
| 25 GbE TCP through host memory | ~3 GB/s | ~1.8 s |

Prefilling 32,000 tokens takes on the order of seconds, so an RDMA transfer is a small fraction of TTFT while TCP would erase the benefit. The figures are line rates; real transfers add overhead. MLA and hybrid models move far less data than this dense example ([chapter 06](06-model-architectures.md)).

## When to disaggregate

| Signal | Leans aggregated | Leans disaggregated |
|---|---|---|
| Input length | Short (a few thousand tokens) | Long (tens of thousands and up), RAG, agent histories |
| Latency SLO | Throughput or TTFT only | Strict p99 ITL while long prompts arrive |
| Input:output ratio | Balanced or output-heavy | Input-heavy |
| Model | Small or dense, fits one node | Large MoE where prefill and decode want different EP/TP |
| Fabric | No RDMA between nodes | GPUDirect RDMA or rack-scale NVLink |
| Team | Early PoC | Able to operate two roles and monitor transfers |

## Variants of the pattern

| Variant | What is split | Status |
|---|---|---|
| **P/D disaggregation** | Prefill vs decode | Production-ready in Dynamo and llm-d. Implemented in [tracks](../tracks/README.md). |
| **E/P/D** | A separate **encode** stage for vision or audio encoders in multimodal models | Supported in recent engine and orchestrator releases |
| **Wide-EP decode** | Decode spread across a rack-scale NVLink domain with large expert parallelism, prefill at smaller EP | Recommended for large MoE (DeepSeek-class) on NVL72 |
| **Attention–FFN disaggregation** | Attention and expert/FFN layers on different GPUs | Research and early implementations |
| **Hardware-specialized phases** | Prefill on compute-dense, context-optimized accelerators; decode on high-bandwidth HBM GPUs | Announced with the Rubin generation (Rubin CPX for context processing) |

## Scaling the two pools

The prefill:decode ratio is the key tuning parameter. Too few prefill workers inflate TTFT; too few decode workers inflate ITL. The right ratio follows from traffic (ISL, OSL, arrival rate) and SLOs ([chapter 09](09-parallelism-and-sizing.md)). It moves as traffic changes, which is why SLO-driven autoscalers (the Dynamo Planner, llm-d's variant autoscaler) scale each pool separately.

## Failure modes to design for

- **Transfer failures:** the decode worker cannot read KV (network, registration or version mismatch). Fail the request visibly, never recompute silently in a benchmark.
- **Role mismatch:** prefill and decode on different model revisions, block sizes or KV dtypes. Pin and verify at startup, and restart both roles together.
- **Pool imbalance:** one pool saturates and its queue dominates latency. Alert on per-pool queue depth.
- **Stranded KV:** cancelled requests leave blocks registered on prefill. Watch memory and the engine's cleanup behavior.

---

**Next:** [04 · Orchestration layer](04-orchestration-layer.md)
