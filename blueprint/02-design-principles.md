# 02 · Design principles

[Home](../README.md) › [Blueprint](README.md) › 02 · Design principles

**Executive summary.** Product-independent rules for LLM serving. Each one names the failure it prevents and where the repository enforces it: digest-pinned images and verified weight revisions, KV-aware routing, separate TTFT/ITL metrics, Kubernetes discovery, and SLO-based sizing. Several are enforced by offline tests.

| What you get from this repository | What you still own |
| --- | --- |
| Principles applied in the manifests, many enforced by `tests/` | Tenant isolation and data-retention policy for prompts and cached KV |

These principles hold whether you run Dynamo or llm-d, and TensorRT-LLM, vLLM or SGLang. Each one names the failure it prevents and where this repository applies it.

| # | Principle | In one line |
|---|---|---|
| 1 | [Start aggregated, earn disaggregation](#1-start-aggregated-earn-disaggregation) | Measure a baseline before adding moving parts |
| 2 | [Split by resource profile, not by habit](#2-split-by-resource-profile-not-by-habit) | Separate what scales differently |
| 3 | [Route to the data](#3-route-to-the-data) | Send requests where their KV cache already is |
| 4 | [Keep tight collectives inside the scale-up domain](#4-keep-tight-collectives-inside-the-scale-up-domain) | TP and wide EP belong on NVLink |
| 5 | [Move KV over RDMA or NVLink, never through the CPU](#5-move-kv-over-rdma-or-nvlink-never-through-the-cpu) | The fabric is part of the architecture |
| 6 | [Treat KV cache as a tiered, first-class resource](#6-treat-kv-cache-as-a-tiered-first-class-resource) | Page it like memory, don't discard it |
| 7 | [Let the model architecture drive the design](#7-let-the-model-architecture-drive-the-design) | KV shape decides parallelism and transfer cost |
| 8 | [Size from SLOs, not from peak FLOPs](#8-size-from-slos-not-from-peak-flops) | TTFT and ITL targets set the P:D ratio |
| 9 | [Pin everything, verify at startup](#9-pin-everything-verify-at-startup) | Mismatched roles fail in the worst ways |
| 10 | [Fail closed](#10-fail-closed) | Never let a broken path silently degrade |
| 11 | [Observe each phase separately](#11-observe-each-phase-separately) | TTFT, ITL and transfer are different problems |
| 12 | [Keep the control plane boring](#12-keep-the-control-plane-boring) | Stateless frontends, HA discovery, standard APIs |
| 13 | [Protect cached state like data](#13-protect-cached-state-like-data) | KV cache encodes prompts |

---

### 1. Start aggregated, earn disaggregation
Disaggregation adds a network hop per request, two roles that must match, and transfer monitoring. For short prompts and balanced traffic, aggregated replicas with KV-aware routing often match it. **Deploy aggregated first, measure, then disaggregate on the same GPUs and compare.**
*Here:* [tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated](../tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/) is the baseline for every disaggregated track, and [benchmarks/](../benchmarks/) compares them with one dataset.

### 2. Split by resource profile, not by habit
Prefill is compute-bound and decode is memory-bandwidth-bound. When they share GPUs, each gets the wrong batch size and they interfere with each other. Split them only when both phases are substantial at the same time and a tight tail-ITL SLO makes that interference expensive. Long inputs alone are not enough: prefill-dominated traffic was faster aggregated on the H200 site ([chapter 11](11-decision-guide.md), [chapter 12](12-results-and-reconciliation.md)).

### 3. Route to the data
Recomputing a prefix that another worker already holds wastes GPU time. A **KV-aware router** scores workers by prefix overlap and load, using KV-cache events from the engines. Round-robin load balancing across LLM workers wastes cache.
*Here:* every Dynamo track runs `--router-mode kv` with engines publishing KV events. llm-d's endpoint picker does the same with its prefix scorer.

### 4. Keep tight collectives inside the scale-up domain
Tensor parallelism all-reduces at every layer, and expert parallelism exchanges tokens all-to-all at every MoE layer. Both need NVLink bandwidth. Keep TP inside a server's NVLink domain, and use rack-scale NVLink (NVL72) for wide EP. Pipeline parallelism and P/D transfers tolerate the scale-out fabric ([chapter 09](09-parallelism-and-sizing.md)).

### 5. Move KV over RDMA or NVLink, never through the CPU
A 32K-token prompt can produce gigabytes of KV cache. Over GPUDirect RDMA on eight 800 Gb/s rails that takes milliseconds; over TCP through host memory it takes seconds. Use one NIC per GPU (rail-optimized), GPUDirect RDMA, and NIXL/UCX pinned to the InfiniBand or RoCE devices ([chapter 07](07-hardware-network-storage.md)).
*Here:* the disaggregated tracks pin `UCX_NET_DEVICES` to the eight `mlx5_*` rails, and every deploy guide includes a step that proves KV moved over InfiniBand.

### 6. Treat KV cache as a tiered, first-class resource
GPU memory holds only the active working set. Evict KV to host DRAM, local NVMe (read back with GPUDirect Storage) or shared storage instead of discarding it. Reload is cheaper than recompute whenever the reload time is below the prefill time ([chapter 08](08-kv-cache-and-offloading.md)).

### 7. Let the model architecture drive the design
MLA models move a small latent KV; hybrid Mamba models move per-sequence state too; MoE models need expert parallelism; sliding-window models bound KV growth. Pick parallelism, transfer backend and cache sizing per architecture, not per habit ([chapter 06](06-model-architectures.md)).

### 8. Size from SLOs, not from peak FLOPs
Start from the traffic (arrival rate, ISL, OSL, prefix reuse) and the SLOs (p99 TTFT, p99 ITL). Measure per-worker prefill and decode throughput *at* those SLOs, then derive worker counts and the P:D ratio ([chapter 09](09-parallelism-and-sizing.md)).

### 9. Pin everything, verify at startup
Prefill and decode must agree on model revision, TP size, KV block size and KV dtype, or the transferred KV is garbage. Pin container images by digest and checkpoints by commit SHA, and **check them when the worker starts**.
*Here:* every reference worker refuses to start if `/model/DEPLOYED_REVISION` differs from the pinned SHA. Offline tests check that prefill and decode flags match.

### 10. Fail closed
A router that silently falls back to aggregated serving, or a decode worker that silently recomputes when a KV load fails, hides real faults and corrupts benchmarks. Configure failures to surface.
*Here:* the llm-d router runs `failureMode: FailClose` and vLLM decode uses `kv_load_failure_policy=fail`. Workers have no restart loop during bring-up, and the benchmark runner stops a sweep on invalid measurements.

### 11. Observe each phase separately
TTFT reflects queueing, prefill and transfer. ITL reflects decode. KV transfer has its own latency and error counters. A single "latency" number hides which pool to scale ([chapter 10](10-production-operations.md)).

### 12. Keep the control plane boring
Frontends should be stateless and replicated. Prefer Kubernetes-API discovery, the Dynamo 1.4.0 operator default, over a separate etcd; a single etcd watch failure dropped every worker from the lab frontend ([troubleshooting](../reference/troubleshooting.md)). Use standard APIs (OpenAI-compatible, Gateway API) so the control plane can be replaced without touching applications.

### 13. Protect cached state like data
KV cache is a function of the prompt. Prefix sharing across tenants, offloaded KV on disks, and shared KV storage all need tenant isolation, encryption at rest, and retention policies, just like the prompts themselves.

---

**Next:** [03 · The disaggregation pattern](03-disaggregation-pattern.md)
