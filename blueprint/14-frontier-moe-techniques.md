# 14 · What makes frontier MoE models fast: the Kimi K3 case

[Home](../README.md) › [Blueprint](README.md) › 14 · Frontier MoE techniques

**Executive summary.** Kimi K3 has 2.8T parameters and still decodes at 110–120 tokens/s
per user without speculation, and 370–423 with it. No single trick gets it there. The speed
comes from a stack of levers that multiply. **Architecture:** hybrid linear attention (69 KDA
layers, 24 MLA) keeps per-sequence memory small; 16 of 896 experts are active per token; the
weights are native MXFP4. **Kernels:** fused KDA, MLA and MoE paths. **Parallelism:** a
different layout for each phase. **Decode:** speculative decoding with a block-parallel
drafter (DSpark). **Serving:** P/D disaggregation and hybrid-aware prefix caching. Every K3
number here is vendor- or community-reported on GB300 and has **not** been reproduced in this
repository. The levers transfer to DeepSeek-, Qwen- and Nemotron-class models.

| What you get from this repository | What you still own |
| --- | --- |
| The levers, what each buys, which transfer to your model, and how K3 maps to the H200 and B300 sites here | Validating any of it on your hardware; the K3 profile in [configs/models.yaml](../configs/models.yaml) is UNVALIDATED |

## The model

| Property | Kimi K3 | Why it matters for serving |
|---|---|---|
| Parameters | 2.8T total, 104B active (3.7%) | Weight **storage** follows 2.8T; per-token **compute** follows 104B |
| Layers | 93: 69 Kimi Delta Attention (KDA) + 24 Gated MLA; 1 dense layer | Only 24 layers keep a KV cache that grows with context |
| Experts | 896 routed, 16 active, 2 shared (Stable LatentMoE) | Very sparse: decode needs large batches per expert, which means wide EP |
| Precision | MXFP4 weights, MXFP8 activations, quantization-aware from SFT onward | Half the bytes of FP8 per weight read; native FP4 tensor cores on Blackwell |
| Context | 1,048,576 tokens | KV size for full-attention layers becomes the long-context limit |
| Checkpoint | About 1.5–1.7 TB | Does not fit in 8 × H200 HBM (1.13 TB) |

Sources: [model card](https://huggingface.co/moonshotai/Kimi-K3),
[vLLM recipe](https://recipes.vllm.ai/moonshotai/Kimi-K3).

## The levers, and what each buys

| # | Lever | What it does | Reported effect on K3 | Transfers to |
|---|---|---|---|---|
| 1 | **Hybrid linear attention (KDA : MLA ≈ 3 : 1)** | KDA layers keep a fixed-size recurrent state per sequence instead of a KV cache that grows with context | SGLang reports about 54 MB of KDA state under TP8 and about 27 KB of MLA KV per token. The Kimi Linear report claims up to 75% less KV cache and up to 6× decoding throughput at 1M context for the same KDA + MLA design | Qwen3-Next, Nemotron-H / Nemotron 3 (Mamba), other hybrids |
| 2 | **MLA for the full-attention layers** | Caches a compressed latent per token; FP8 KV with prefill query quantization (`TOKENSPEED_MLA`) | Small KV and small P/D payload | DeepSeek V3/V4, Kimi K2 |
| 3 | **Extreme MoE sparsity** | Only 16 of 896 experts run per token | Decode reads a small share of the weights per token. The batch must be large and spread with EP so each expert does useful work | All large MoE |
| 4 | **Native low precision (MXFP4, trained in)** | 4-bit weights without post-hoc quality loss; MoE GEMMs run natively in MXFP4 (TRT-LLM-Gen kernels under TP, MegaMoE under P/D) | Halves weight bandwidth versus FP8 | Any model shipped as NVFP4/MXFP4 on **Blackwell**. On Hopper, FP4 is dequantized (Marlin), so most of the gain is lost |
| 5 | **Fused kernels and launch elimination** | KDA decode folds convolution, recurrent update and RMSNorm into one launch; Attention Residuals fused; communication fused and overlapped | SGLang batch-1 decode went from about 63.8 to about 113 tok/s (1.77×) from engineering alone | Every model: why the engine version matters as much as the engine |
| 6 | **Phase-specific parallelism** | Prefill: chunked pipeline parallel PP8×TP1 (SGLang), or TEP8 with custom reduce-scatter/all-gather (vLLM). Decode: TP8, DCP8 or DEP16 | SGLang PP8 prefill reaches 1.7× the TEP8 prefill ceiling; vLLM's collectives are 1.7–4.5× faster than NCCL at small and medium sizes | Large MoE under P/D ([chapter 09](09-parallelism-and-sizing.md)) |
| 7 | **Decode context parallelism (DCP)** | Shards the latent KV by **position** across decode ranks, with one all-to-all per MLA layer, instead of every TP rank holding a full copy | SGLang reports 7.9× more logical KV capacity with DCP8: more and longer sequences per decode worker | Any MLA model at long context (DeepSeek too) |
| 8 | **Speculative decoding (DSpark)** | A 2B, 5-layer block-diffusion drafter proposes 7 tokens in one pass ([chapter 13](13-speculative-decoding.md)) | vLLM 118 → 370 tok/s (3.14×) at batch 1 on 16 GB300; SGLang about 423 tok/s on GSM8K | Any model with an MTP or trained drafter |
| 9 | **P/D disaggregation** | Prefill and decode on separate pools, each with lever 6's layout, KV over NIXL | SGLang 2,808 output tok/s per GPU (PP8 prefill + TP8 decode, FP4); 2,633 with DCP8 decode | Large MoE at scale ([chapter 03](03-disaggregation-pattern.md)) |
| 10 | **Hybrid-aware prefix caching** | Snapshots KDA state at block boundaries and branch points (copy-on-write). Interval checkpoints, such as one every 32K tokens, plus prompt boundaries. Marconi-style "cache on second hit" admission | Multi-turn and agent prefixes hit even though the recurrent state cannot be sliced like KV | All hybrid SSM / linear-attention models |

Sources: [vLLM K3 post](https://vllm.ai/blog/2026-07-27-k3),
[LMSYS / SGLang K3 post](https://www.lmsys.org/blog/2026-07-27-kimi-k3-day0-support/),
[Kimi Linear report](https://arxiv.org/abs/2510.26692),
[RadixArk DSpark card](https://huggingface.co/RadixArk/Kimi-K3-DSpark). The InferenceX
figures that the vLLM recipe cites are SemiAnalysis's, and the recipe says it has not
reproduced them.

### Why the levers multiply

Decode time per token is roughly *bytes read per step ÷ HBM bandwidth*, divided by the
tokens produced per step:

- **Fewer bytes per sequence:** levers 1, 2 and 7 shrink the KV and state each step must read.
- **Fewer bytes per weight:** lever 4.
- **Fewer weights per token:** lever 3, at the cost of needing wide EP to keep experts busy.
- **Less overhead per step:** lever 5.
- **More tokens per step:** lever 8.

Prefill gets levers 4, 5 and 6, and lever 10 avoids prefill entirely on cache hits. Lever 9
lets prefill and decode each use their own best layout without competing for the same GPUs.

## Two operating points, not one

The published K3 numbers come from two different configurations. Do not quote them together.

| Goal | Metric | Configuration | Reported |
|---|---|---|---|
| **Interactivity** | tok/s per user | Small batch, TP8 or TP16 decode, DSpark on with 7 draft tokens | 331–423 tok/s per user |
| **Throughput** | tok/s per GPU | P/D, PP8 prefill, TP8/DCP8 or DEP16 decode, large decode batch, speculation reduced or off | 2,808 tok/s per GPU |

A deployment sits somewhere on the curve between them. The SLO decides where: a coding
assistant buys interactivity, a batch summarizer buys throughput. SGLang's interactive mode
(one PP8 prefill feeding several decode instances) held above 116 tok/s per user, which
shows that P/D and speculation can coexist on the same graph.

## NVIDIA's Dynamo reference for K3

The Dynamo K3 recipe at the reviewed commit
([deploy.yaml](https://github.com/ai-dynamo/dynamo/blob/6822babc5c542350127e490f4fb8f2042855559c/recipes/kimi-k3/vllm/disagg-gb300-agentic/deploy.yaml))
is an **agentic** P/D graph on GB300:

| Setting | Prefill | Decode |
|---|---|---|
| Workers × GPUs | 1 × TP8 (2 nodes × 4 GB300) | 1 × TP8 (2 nodes × 4 GB300) |
| `max-num-seqs` | 16 | 128 |
| `max-num-batched-tokens` | 16,384 | 2,048 |
| Speculation | — | DSpark, 7 tokens (`synthetic_acceptance_length` 4.2584 for benchmarking) |
| KV transfer | `NixlConnector` | `NixlConnector` |
| Agent features | — | `kimi_k3` tool and reasoning parsers, `--dyn-enable-structural-tag` |

The decode batch-token cap (2,048) is small on purpose: with 128 sequences and 8 verify
positions each, a decode step already holds about 1,024 tokens.

## K3 on this repository's hardware

| Site | Fits? | Assessment (design reasoning, UNVALIDATED) |
|---|---|---|
| 2 × HGX H200 (16 × 141 GB = 2.26 TB) | Only across both nodes (TP8 × PP2 or TEP16), leaving little HBM for KV | Not recommended. No FP4 tensor cores, so MXFP4 runs dequantized, and the TP or EP traffic between the two nodes crosses InfiniBand |
| 2 × HGX B300 (8 × 288 GB = 2.3 TB per node) | One node holds the weights with several hundred GB left for KV | Aggregated TP8 per node, or 1P + 1D TP8 across nodes over InfiniBand. The latter is this repository's K3 profile ([reference/models.md](../reference/models.md#compatibility-limits)). Each node has about the same HBM as the "8 × GB300" minimum, but the NVLink domain is 8 GPUs, not 72 |
| GB300 NVL72 | Yes, with room for DEP16 decode and multi-node TP inside NVLink | The reference platform for every published K3 number |

Recommended bring-up order on B300: aggregated TP8 without speculation, then add DSpark at
concurrency 1–16 and measure acceptance on real prompts, then P/D. The validation track is
[tracks/nvidia-dynamo/studies/planned/09](../tracks/nvidia-dynamo/studies/planned/09-b300-reference-validation/), and K3 is not yet in it.

## Transferable lessons

| If your model is… | Borrow these levers |
|---|---|
| Large MoE with MLA (DeepSeek V3/V4, Kimi K2) | 2, 3, 6, 7, 8 (native MTP/NextN), 9 |
| Hybrid SSM or linear attention (Nemotron 3, Qwen3-Next) | 1, 10. Check that speculation supports state rollback for the family |
| Shipped in NVFP4/MXFP4 | 4, but only on Blackwell or newer |
| Any model on a new engine release | 5: re-measure after every engine upgrade; kernel work alone moved K3 1.77× |
| Serving agents or coding | 8 (high acceptance), 10 (deep prefix reuse), and KV-aware routing ([chapter 15](15-workload-driven-design.md)) |

---

**Next:** [15 · Workload-driven design](15-workload-driven-design.md)
