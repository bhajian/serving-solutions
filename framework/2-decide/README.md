# 2 · Decide: pattern, layout, track and path

[Home](../../README.md) › [Framework](../README.md) › 2 · Decide

**Output:** a design record ([template](design-record.template.md)). **Gate:** every decision
cites the row it came from and, where one exists, a study. Take the four decisions in order;
each narrows the next.

| # | Decision | Driven by | Rationale lives in |
| --- | --- | --- | --- |
| D1 | **Serving pattern**: aggregated, prefix-aware routing, KV tiering, P/D, wide EP, admission control, autoscaling | Workload, goal, SLO, fleet size, fabric | [blueprint 11](../../blueprint/11-decision-guide.md), [15](../../blueprint/15-workload-driven-design.md) |
| D2 | **Model layout**: worker size, TP/EP/DP attention, precision, speculation | Model architecture and size, hardware | [blueprint 09](../../blueprint/09-parallelism-and-sizing.md), [13](../../blueprint/13-speculative-decoding.md), [15 §3](../../blueprint/15-workload-driven-design.md#3-model-type-and-size) |
| D3 | **Solution track**: NVIDIA Dynamo or llm-d with Red Hat AI | Constraints, required patterns, support | [blueprint 04](../../blueprint/04-orchestration-layer.md), [tracks](../../tracks/README.md) |
| D4 | **Implementation path**: the graph, overlay or well-lit path that implements D1 on D3 | D1 × D3 | The pattern map below |

## D1 · Serving pattern

Start from the workload class, then let the goal and SLO add or remove patterns.

| Workload ([profiles](../../blueprint/15-workload-driven-design.md#4-workload-types)) | Start with | Add when |
| --- | --- | --- |
| Multi-turn chat | Aggregated replicas + prefix-aware routing | KV tiering when idle sessions exceed HBM; P/D only at 6+ workers with a tight ITL SLO |
| RAG / document QA (long ISL, low reuse) | Aggregated, large prefill chunks | Context-parallel prefill at ≥ 128K if TTFT misses; P/D if ITL is tight and 5+ workers |
| Agent tool loop (very high reuse) | Prefix-aware routing **first**, prefix caching | KV tiering (mandatory at scale), then P/D at scale |
| Agentic coding | Prefix-aware routing, speculative decoding | P/D at scale; KV tiering |
| Reasoning / thinking (short in, long out) | Aggregated, speculative decoding | DP attention / DCP for MLA decode capacity |
| Code completion (tiny requests, p99 TTFT) | Aggregated, prefix-aware routing | — (handoff never amortizes) |
| Batch / offline | Aggregated, maximum batch | Wide EP for large MoE; queue-based admission |

Then check the P/D preconditions; all six must hold, or stay aggregated
([blueprint 11](../../blueprint/11-decision-guide.md#when-disaggregation-wins)): both phases substantial
(0.15 ≲ *R* ≲ 7), tight p99 ITL, tunable P:D (fleet ≥ 1 + max(*R*, 1/*R*) workers), per-phase
parallelism, working KV-aware routing, RDMA or NVLink for the handoff. **Measure routing before
deciding P/D:** a high cache hit rate can move the workload out of the P/D window.

## Optimization goals

| Goal | Accept on | Patterns and levers that move it | Prove it with |
| --- | --- | --- | --- |
| **Long context** (ISL ≥ 64K, TTFT-bound) | TTFT p50/p99 split by first turn and follow-up turns; cache hit rate; wall time | Prefix-aware routing, prefix caching, large prefill chunks, context-parallel prefill, KV tiering. Aggregated usually beats P/D here. | 256K studies: [Dynamo agg vs P/D](../../tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/README.md), [llm-d routing](../../tracks/llm-d-redhat/studies/deepseek-v4-pro-256k-routing/README.md) |
| **Output-optimized** (long OSL, decode-bound) | Per-user tokens/s, TPOT, worst-case ITL, stalls | Speculative decoding, FP8 KV, DP attention / DCP, P/D to remove prefill stalls from decode | [8K in / 128K out study](../../tracks/nvidia-dynamo/studies/nemotron-3-nano-8k-128k-comparison/README.md) |
| **SLA-optimized** (goodput at p99) | Goodput (requests/s meeting p99 TTFT and ITL), SLO attainment | P/D with a tunable ratio, SLO-driven autoscaling, admission control, prefix-aware routing | Open-loop goodput sweep ([planned 01](../../tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/README.md)) |
| **Throughput and cost** (batch) | Output tokens/s per GPU, cost per million tokens | Maximum batch, aggregated, wide EP, FP8/FP4 | Closed-loop `loadgen` with `--gpu-hour-usd` ([benchmarks](../../benchmarks/README.md)) |

## D2 · Model layout

| Model class | Worker | Layout notes | Speculation |
| --- | --- | --- | --- |
| Dense ≤ ~15B | TP1, many replicas | Replicas over TP; prefix-aware routing | EAGLE-3 / n-gram |
| Dense 30–70B | TP2–TP4 (H200), TP1–TP2 (B300 FP8/FP4) | FP8 KV; chunked prefill tuning | EAGLE-3 or same-family draft |
| Small MoE (30B-A3B class) | TP1–TP4 | Many small workers keep P:D tunable | MTP if shipped |
| Large MoE 200–500B | One node, TP8 / EP8 | EP, FP8, DP attention if supported | EAGLE-3 / MTP |
| Frontier MoE + MLA ≥ 600B | Full node (H200: weights alone need 8 GPUs) to NVL72 | Prefill small TP + EP; decode wide EP + DP attention at scale; TP8 for bring-up | Native MTP / DSpark where the engine supports it on the hardware |
| Hybrid SSM | Per size class | Snapshot-aware prefix caching | Only with state rollback support |

Size TP from weights plus KV, never from the GPU count of a node
([blueprint 09](../../blueprint/09-parallelism-and-sizing.md)). Stage 3 checks the numbers.

## D3 · Solution track

| If the profile says… | Track |
| --- | --- |
| OpenShift, or Red Hat support and subscriptions are required | [llm-d + Red Hat AI](../../tracks/llm-d-redhat/README.md) |
| Kubernetes platform standardizing on the Gateway API Inference Extension | llm-d + Red Hat AI |
| Non-NVIDIA accelerators in the fleet (AMD, TPU, Gaudi) | llm-d (vLLM backends) |
| TensorRT-LLM required, or Docker hosts without Kubernetes | [NVIDIA Dynamo](../../tracks/nvidia-dynamo/README.md) |
| SLO-driven P/D autoscaling (Planner) and multi-tier KV (KVBM) from one vendor; NVIDIA AI Enterprise support | NVIDIA Dynamo |
| Both acceptable | The track whose implementation of the D1 pattern has the higher status in the map below; or run the same study on both |

**Support is a property of the platform, not only the software.** Red Hat supports its llm-d
distribution on OpenShift AI and on selected managed Kubernetes services; the standalone
Red Hat AI Inference Server container on other Kubernetes falls under third-party policy
([llm-d track](../../tracks/llm-d-redhat/README.md#support-and-platforms)). Confirm the support
statement for the customer's exact platform before committing.

## D4 · Pattern → implementation map

Status: **validated** (measured here), **deployed** (running, study in progress), **reference**
(manifests pass offline tests), **planned** (guide stub).

| Pattern (D1) | NVIDIA Dynamo | Status | llm-d + Red Hat AI | Status |
| --- | --- | --- | --- | --- |
| Aggregated replicas | [graphs/*/aggregated](../../tracks/nvidia-dynamo/graphs/README.md) | validated (lab) | [01 optimized baseline](../../tracks/llm-d-redhat/paths/01-optimized-baseline/README.md) | deployed |
| Prefix / KV-aware routing (approximate) | KV router (`--router-mode kv`) | validated (lab) | [01 optimized baseline](../../tracks/llm-d-redhat/paths/01-optimized-baseline/README.md) | deployed |
| Prefix routing on exact KV events | KV router with engine KV events | validated (lab) | [02 precise prefix-cache routing](../../tracks/llm-d-redhat/paths/02-precise-prefix-cache-routing/README.md) | planned |
| Latency-predictive routing | — | — | [03 predicted-latency routing](../../tracks/llm-d-redhat/paths/03-predicted-latency-routing/README.md) | planned |
| KV tiering / offload | KVBM | roadmap | [04 tiered prefix cache](../../tracks/llm-d-redhat/paths/04-tiered-prefix-cache/README.md) | planned |
| P/D disaggregation | [graphs/*/disaggregated](../../tracks/nvidia-dynamo/graphs/README.md) + NIXL | validated (lab) | [05 P/D disaggregation](../../tracks/llm-d-redhat/paths/05-pd-disaggregation/README.md) | reference (B300) |
| Wide EP + DP attention | SGLang DP attention + EP ([planned 05](../../tracks/nvidia-dynamo/studies/planned/05-deepseek-layout/README.md)) | planned | [06 wide EP](../../tracks/llm-d-redhat/paths/06-wide-ep/README.md) | planned |
| Admission control, multi-tenant queuing | Gateway rate limits ([production](../../tracks/nvidia-dynamo/production/README.md)) | reference | [07 flow control](../../tracks/llm-d-redhat/paths/07-flow-control/README.md) | planned |
| SLO-driven autoscaling | Planner ([planned 03](../../tracks/nvidia-dynamo/studies/planned/03-planner-demo/README.md)) | reference | [08 workload autoscaling](../../tracks/llm-d-redhat/paths/08-workload-autoscaling/README.md) | planned |

---

**Next:** [3 · Size](../3-size/README.md)
