# 01 · Aggregated serving (baseline)

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Sites](../../README.md) › [hgx-b300-2x8](../README.md) › 01 · Aggregated

**Goal:** deploy the simplest production-shaped topology, where every worker serves complete requests, and measure it. This is the **baseline** for every disaggregated track.

![Aggregated vs disaggregated serving: aggregated replicas run prefill and decode on the same GPUs, so long prefills stall decoding; disaggregation separates the phases and adds a KV-cache transfer](../../../../../assets/diagrams/png/agg-vs-disagg.png)

This track deploys the **left** half of the picture. The blueprint explains the pattern in [03 · Disaggregation pattern](../../../../../blueprint/03-disaggregation-pattern.md).

## Pick your engine and platform

| Engine | Docker Compose | Kubernetes |
|---|---|---|
| **vLLM** (reference) | [vllm/docker](../compose/01-aggregated/vllm/) | [vllm/kubernetes](vllm/) |
| **SGLang** | [sglang/docker](../compose/01-aggregated/sglang/) | [sglang/kubernetes](sglang/) |

Use the **same engine** here as in the disaggregated track you will compare against: [02](../02-dynamo-disagg-vllm/) for vLLM, [03](../03-dynamo-disagg-sglang/) for SGLang.

**One node or two?**

- **One node (learning):** start only Node A. You get etcd, the frontend and one replica, and the router still works.
- **Two nodes (fair baseline):** add the Node B replica. It uses the **same 16 GPUs** as the disaggregated tracks, so throughput is comparable.

## What runs, and why

| Component | Node | What it does |
|---|---|---|
| `etcd` | A | Registry. Each worker announces its endpoint, and the frontend discovers workers here. |
| `frontend` | A | OpenAI-compatible API on :8000. Tokenizes, applies the chat template and routes each request by KV-cache overlap. |
| `worker` | A (and B) | `python -m dynamo.vllm` or `dynamo.sglang`: the engine on 8 GPUs with tensor parallelism 8 |

Aggregated workers need **no InfiniBand devices, no privileged mode and no NIXL**, because nothing crosses nodes except control traffic. Compare these files with [02](../02-dynamo-disagg-vllm/) to see exactly what disaggregation adds.

## The worker command, explained (vLLM)

These flags appear in [vllm/docker/node-a.yaml](../compose/01-aggregated/vllm/node-a.yaml) and [vllm/kubernetes/30-worker.yaml](vllm/30-worker.yaml).

| Flag | Value | Why |
|---|---|---|
| `--model` / `--served-model-name` | `/model`, the HF id | Local weights, and the API name clients must send |
| `--tensor-parallel-size` | 8 | Shard every layer across the 8 NVLink-connected GPUs of one node |
| `--no-enable-expert-parallel` | | Keep MoE experts tensor-parallel, as in NVIDIA's recipe for this model |
| `--max-model-len` | 32768 | Context window served. Start small, then raise it once stable. |
| `--max-num-seqs` | 32 | Maximum concurrent sequences in a batch |
| `--max-num-batched-tokens` | 8192 | Per-step token budget. This makes prefill **chunked**, which limits how long a big prompt stalls decodes. |
| `--gpu-memory-utilization` | 0.80 | Share of HBM for weights plus KV cache. The rest is headroom. |
| `--block-size` | 64 | KV page size in tokens. **Must equal** the frontend's `--kv-cache-block-size`. |
| `--kv-cache-dtype` | fp8 | Halves KV memory compared with BF16 |
| `--enable-prefix-caching` | | Reuse KV blocks for repeated prefixes. The KV-aware router depends on it. |
| `--attention-backend` … `--async-scheduling` | | Nemotron 3 Ultra's hybrid Mamba + attention kernels, from NVIDIA's recipe |
| `--reasoning-parser*`, `--dyn-*-parser` | | Split reasoning text and tool calls into OpenAI-compatible fields |
| `--kv-events-config` | ZMQ publisher | The worker reports cache changes, so the router knows who holds which prefix |

SGLang uses equivalent flags under different names. See [reference/vllm-vs-sglang.md](../../../../../reference/vllm-vs-sglang.md).

## What to observe

1. **Throughput scales with replicas.** Benchmark with Node A alone, then with both nodes, at the same concurrency.
2. **Prefix-cache routing.** Repeat a long prompt. The second response has much lower TTFT and is served by the same replica.
3. **Phase interference.** At concurrency 8 with long prompts, look at `itl_ms_p99` and `tpot_ms`. Stalls from prefill competing with decode show up there, and that is the effect disaggregation targets.

---

**Next:** [02 · Dynamo disaggregated · vLLM](../02-dynamo-disagg-vllm/) · [03 · Dynamo disaggregated · SGLang](../03-dynamo-disagg-sglang/)
