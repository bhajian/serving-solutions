# 11 · Decision guide

[Home](../README.md) › [Blueprint](README.md) › 11 · Decision guide

**Executive summary.** Choose the topology first, from the workload, the SLO, how far the
P:D ratio can be tuned, and the fabric. Then choose the engine and the control plane.
Disaggregation wins only when all of its preconditions hold. Otherwise aggregated
replicas with KV-aware routing are faster and simpler. On two HGX H200 servers with TP8
workers, aggregated plus the KV router is usually the right answer; the three measured
studies on that site agree ([chapter 12](12-results-and-reconciliation.md)).

| | What you get from this repository | What you still own |
| --- | --- | --- |
| Decision | The criteria below, the measured H200 evidence, and prepared experiments to test your own region | Your traffic profile, SLOs and fleet size |
| Implementation | Operator-managed aggregated and disaggregated graphs ([tracks/nvidia-dynamo/graphs](../tracks/nvidia-dynamo/graphs/)) | Choosing and validating the P:D ratio for your load |

![Choosing a serving design: decision flow from workload to topology, then engine and control plane](../assets/diagrams/png/decision-flow.png)

## When disaggregation wins

Use disaggregated serving only when **all** of the following hold (design guidance; the
measured counter-examples are in [chapter 12](12-results-and-reconciliation.md)):

1. **Both phases are substantial and concurrent.** At peak load, prefill and decode each
   take a large share of GPU time at the same time. Prefill-dominated traffic (very long
   prompts, short answers) and decode-dominated traffic (short prompts, very long
   generations) both favoured aggregated on the H200 site.
2. **The p99 ITL SLO is tight.** In aggregated batches, prefill chunks stall running
   streams; that becomes an SLO miss only when the ITL target is tight. The 8K/128K
   study measured stalls of up to 13 s aggregated, and none disaggregated.
3. **The P:D ratio is tunable.** You can run enough workers to choose a ratio that
   matches the traffic: four or more nodes, or several workers per node (TP2/TP4 on
   8-GPU nodes). The Dynamo Planner can then follow the load. A fixed 1P:1D on two nodes
   halves prefill capacity.
4. **Each phase gets its own parallelism.** For MoE and MLA models, prefill uses small TP
   (plus EP) and decode uses wide EP with DP attention
   ([pd-parallelism](../assets/diagrams/png/pd-parallelism.png)).
5. **KV-aware routing works.** The router balances load and keeps prefix reuse; verify
   both ([tracks/nvidia-dynamo/studies/planned/02](../tracks/nvidia-dynamo/studies/planned/02-kv-router/)).
6. **The fabric makes the handoff cheap.** GPUDirect RDMA over InfiniBand or RoCE, or an
   NVLink domain. Over TCP, the transfer can cost more than it saves.

A quantitative version of criteria 1 and 3 is the prefill-to-decode work ratio *R* and the
minimum worker count to express it, with transfer intensity by model class
([chapter 15](15-workload-driven-design.md)). Disaggregation is a candidate when
0.15 ≲ *R* ≲ 7 and the fleet has at least 1 + max(*R*, 1/*R*) workers.

![When disaggregation wins](../assets/diagrams/png/when-disaggregation-wins.png)

## Questions, in order

1. **What is the model?** Family, size and precision ([chapter 06](06-model-architectures.md)).
   This fixes KV bytes per token and which parallelism fits. Size TP from the weights
   and KV, not from the GPU count: Nemotron 3 Nano (30B-A3B) fits on one H200, so TP2–TP4
   workers leave room to tune P:D, while TP8 does not.
2. **What is the hardware domain?** 8-GPU servers or rack-scale NVLink, and whether
   GPUDirect RDMA is available ([chapter 07](07-hardware-network-storage.md)).
3. **What is the traffic?** ISL and OSL distributions, arrival rate, prefix reuse, and the
   p99 TTFT and ITL targets. Measure goodput at those targets with
   [benchmarks/loadgen](../benchmarks/README.md).
4. **Which topology?** Apply the six criteria above.
5. **Which engine?** From model support, quantization and features (MTP, DP attention, KV
   transfer backend), measured on your hardware ([chapter 05](05-inference-engines.md),
   [engine flags](../reference/engine-flags.md)).
   Then decide on speculative decoding from the workload's acceptance and the decode
   concurrency ([chapter 13](13-speculative-decoding.md)), and on the other advanced methods
   from the workload matrix ([chapter 15](15-workload-driven-design.md#5-which-advanced-methods-for-which-workload)).
6. **Which control plane?** The Dynamo operator (graphs, Planner, KV router) or llm-d
   (Gateway API Inference Extension) ([chapter 04](04-orchestration-layer.md)).
7. **Does KV need tiers?** Yes, if reusable prefixes exceed GPU memory ([chapter 08](08-kv-cache-and-offloading.md)).

## Reference scenarios

| Scenario | Topology | Engine | Start from | Status |
| --- | --- | --- | --- | --- |
| **Chat or agents on 2 × HGX H200**, any SLO | Aggregated replicas, KV-aware router | SGLang | [nemotron-3-nano aggregated](../tracks/nvidia-dynamo/production/nemotron-3-nano-h200/aggregated/) | Topology validated (tracks/nvidia-dynamo/studies/); operator path UNVALIDATED |
| **Mixed ISL/OSL with a tight p99 ITL SLO**, 4+ nodes or TP2/TP4 workers, InfiniBand | Disaggregated, Planner-managed P:D | SGLang or vLLM | [nemotron-3-nano disaggregated](../tracks/nvidia-dynamo/production/nemotron-3-nano-h200/disaggregated/) | UNVALIDATED: [tracks/nvidia-dynamo/studies/planned/01](../tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/), [03](../tracks/nvidia-dynamo/studies/planned/03-planner-demo/) |
| **Large MoE / MLA** (DeepSeek-, Kimi-class) | Disaggregated; decode with wide EP + DP attention; MTP | SGLang or TensorRT-LLM | [tracks/nvidia-dynamo/studies/planned/05](../tracks/nvidia-dynamo/studies/planned/05-deepseek-layout/) | UNVALIDATED |
| **Frontier hybrid MoE** (Kimi K3, 2.8T MXFP4) | Aggregated TP8 per B300 node for bring-up; P/D with DSpark speculation at scale, ideally on NVL72 | vLLM or SGLang (K3 patched images) | [chapter 14](14-frontier-moe-techniques.md), `kimi-k3` in [configs/models.yaml](../configs/models.yaml) | UNVALIDATED |
| **Agentic coding** (long, highly reused context; long diffs) | KV-aware routing and prefix caching first; P/D at scale; speculative decoding on | SGLang or vLLM | [chapter 15](15-workload-driven-design.md) | Design guidance |
| **Reasoning / thinking models** (short prompt, 8–64K output) | Aggregated; speculative decoding on; decode KV capacity (FP8 KV, DCP) | any | [chapter 13](13-speculative-decoding.md) | Design guidance |
| **Very long prompts, short answers** (256K RAG) | Aggregated; larger prefill chunks | SGLang | [deepseek-v4-pro aggregated](../tracks/nvidia-dynamo/production/deepseek-v4-pro-h200/aggregated/) | Validated on H200 (lab path) |
| **Multi-turn heavy reuse** | Any of the above + KV tiers | engine with an offload connector | [chapter 08](08-kv-cache-and-offloading.md) | Roadmap |
| **Kubernetes platform standardizing on Gateway API Inference Extension** | Per workload | vLLM | [B300 track 04](../tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/) | UNVALIDATED |

## Anti-patterns

| Anti-pattern | Why it hurts | Instead |
| --- | --- | --- |
| Disaggregating at a fixed 1P:1D on two nodes | Halves prefill capacity; aggregated was 1.62× and 5.5× faster on prefill-heavy traffic (tracks/nvidia-dynamo/studies/) | Aggregated, or tune P:D with smaller workers |
| Disaggregating without RDMA | KV transfer over TCP can exceed prefill time | Aggregated with KV-aware routing until the fabric is ready |
| Round-robin load balancing across LLM workers | Throws away prefix-cache locality | KV-aware routing with active-request weighting ([troubleshooting](../reference/troubleshooting.md#kv-router-imbalance-152--120--120--120-requests-per-worker)) |
| Sizing a small model at TP8 because the node has 8 GPUs | All-reduce cost without benefit; no room to tune P:D | TP from weights and KV; more, smaller workers |
| Enabling speculative decoding with a fixed draft length at peak load | Verification compute crowds out other sequences; throughput drops | Load-adaptive draft length, or off above ~16–32 sequences per decode instance ([chapter 13](13-speculative-decoding.md)) |
| Benchmarking speculation on random or forced-length text | Acceptance is understated (random) or inflated (repetition after EOS) | Natural-length runs on real prompts at the production temperature |
| Deciding P/D before enabling KV-aware routing | A 90% prefix hit rate can move the workload out of the disaggregation window | Measure *R* with routing on ([chapter 15](15-workload-driven-design.md)) |
| Judging by tokens/s alone | A configuration can deliver more tokens/s while missing the SLO | Goodput at p99 TTFT and ITL |
| Mixing images or revisions between prefill and decode | Silent KV corruption or crashes | Pin by digest and revision; verify at startup (init container) |
| A single latency number on the dashboard | Hides which pool to scale | TTFT, ITL, queue depth and transfer metrics per pool ([tracks/nvidia-dynamo/observability](../tracks/nvidia-dynamo/observability/)) |

---

**Back to:** [Blueprint index](README.md) · **Evidence:** [chapter 12](12-results-and-reconciliation.md) · **Implement it:** [tracks](../tracks/README.md)
