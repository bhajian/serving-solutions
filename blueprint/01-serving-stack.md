# 01 · The serving stack

[Home](../README.md) › [Blueprint](README.md) › 01 · Serving stack

**Executive summary.** Every LLM serving platform is built from the same layers: API edge, control plane, engine, model, data movement, Kubernetes platform and hardware. Choices in one layer constrain the others. This repository implements NVIDIA Dynamo as the control plane with SGLang (validated on H200) and vLLM (B300 reference) engines on Kubernetes.

| What you get from this repository | What you still own |
| --- | --- |
| A layer map with the pinned version and the repository path that configures each layer | Selecting products per layer for your platform standards |

Every production LLM platform, whatever its vendor, is built from the same seven layers. Naming them makes choices explicit, and it makes clear which choices constrain each other.

![The LLM serving stack](../assets/diagrams/png/serving-stack.png)

## The layers

### Applications
Chat assistants, agents with tool calls, retrieval-augmented generation and offline batch jobs. They matter to the architecture through their **traffic shape**: input length (ISL), output length (OSL), how much prefix they reuse (multi-turn sessions, shared system prompts, shared documents), and their latency targets.

### Access layer
The contract with applications: an **OpenAI-compatible API** (`/v1/chat/completions`, streaming over server-sent events). It also carries authentication, quotas, rate limits and TLS. Keeping this layer stable lets you swap everything below it.

### Serving control plane
The scheduler of the system. It decides **which worker serves which request**, keeps track of **where KV cache lives**, **coordinates prefill and decode** when they are split, **scales** workers against SLOs, and manages worker **lifecycle**. The two leading open implementations are [NVIDIA Dynamo](04-orchestration-layer.md#nvidia-dynamo) and [llm-d](04-orchestration-layer.md#llm-d).

### Inference engine
The runtime inside each worker. It owns the GPU: continuous batching, the paged KV cache, chunked prefill, prefix caching, speculative decoding, attention and GEMM kernels, quantization, and intra-worker parallelism. The three leading open engines are [TensorRT-LLM, vLLM and SGLang](05-inference-engines.md).

### Model architecture
The workload itself. Dense or MoE, GQA or MLA attention, full or sliding-window, Transformer or hybrid Mamba. The architecture determines **how big the KV cache is**, **what disaggregation has to move**, and **which parallelism fits** ([chapter 06](06-model-architectures.md)).

### Data movement & memory
The drivers and virtual memory of the stack:

- **NCCL** handles collectives such as tensor-parallel all-reduce and expert all-to-all.
- **NIXL** moves KV blocks between workers and storage tiers.
- **UCX** is a transport that NIXL uses.
- **GPUDirect RDMA** lets NICs read GPU memory directly.
- **GPUDirect Storage** lets NVMe devices write into GPU memory directly.
- **KV-cache managers** page KV across memory tiers.

### Hardware
GPUs with HBM; a **scale-up fabric** (NVLink/NVSwitch inside a server or an NVL72 rack); a **scale-out fabric** (InfiniBand or RoCE Ethernet, one NIC per GPU); and **storage** attached for weights and KV tiers ([chapter 07](07-hardware-network-storage.md)).

**Cross-cutting:** Kubernetes and its GPU and network operators, observability, security, and the model registry run alongside every layer ([chapter 10](10-production-operations.md)).

## Contracts between layers

The layers stay replaceable only if the interfaces between them are clear.

| Boundary | Contract | Examples |
|---|---|---|
| Application → Access | OpenAI-compatible HTTP + SSE | `/v1/chat/completions`, `/v1/models` |
| Access → Control plane | Authenticated request, tenant, priority | Gateway headers, Gateway API routes |
| Control plane → Engine | Request + routing decision + P/D hand-off metadata | Dynamo request plane (TCP), llm-d sidecar HTTP |
| Engine → Control plane | Health, load, **KV-cache events** (blocks stored or evicted) | Dynamo KV events over ZMQ, llm-d KV-cache indexer, `/metrics` |
| Engine ↔ Engine | KV-cache transfer | NIXL (UCX, GDS backends), vendor connectors |
| Engine → Hardware | Collectives, memory registration, direct I/O | NCCL, GPUDirect RDMA, GPUDirect Storage |

The **KV-cache event** stream is the most important contract. It is how a control plane knows where each prefix lives, and it enables KV-aware routing, tiering and cross-worker reuse.

## Compatibility today

| | TensorRT-LLM | vLLM | SGLang |
|---|---|---|---|
| **NVIDIA Dynamo** | ✓ (`dynamo.trtllm`) | ✓ (`dynamo.vllm`) | ✓ (`dynamo.sglang`) |
| **llm-d** | not a documented path | ✓ primary engine | ✓ guide available |
| **P/D transfer** | cache transceiver (NIXL, UCX) | NIXL connector (plus others) | NIXL or Mooncake backends |

Verify against the pinned versions in [reference/sources.md](../reference/sources.md). Integrations change with every release.

## How this repository implements the stack

| Layer | Implemented in [tracks](../tracks/README.md) |
|---|---|
| Control plane | Dynamo (tracks 01–03), llm-d (track 04) |
| Engine | vLLM, SGLang. TensorRT-LLM is on the [roadmap](../ROADMAP.md). |
| Model | Nemotron 3 Ultra (hybrid Mamba + attention MoE, NVFP4). Qwen3-Coder-480B for llm-d. |
| Data movement | NCCL for TP8, NIXL over UCX for P/D |
| Hardware | 2 × 8 × B300, NVLink inside each node, 8 × 800 Gb/s InfiniBand rails |
| Storage | Local NVMe for weights. KV tiers on the [roadmap](../ROADMAP.md). |

---

**Next:** [02 · Design principles](02-design-principles.md)
