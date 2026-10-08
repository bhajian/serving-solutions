# 13 · Speculative decoding

[Home](../README.md) › [Blueprint](README.md) › 13 · Speculative decoding

**Executive summary.** Speculative decoding drafts several tokens cheaply and verifies them
in one target-model pass. It speeds up decode only while the decode step is memory-bound,
so it is a **per-user latency lever at low to moderate concurrency**, not a throughput
lever at full batch. The gain is set by the acceptance length, which depends on the
workload: code and agent traffic accept 4–5.5 tokens per step with Kimi K3's DSpark draft,
creative chat about 2.6. Checkpoint-native drafts (MTP, NextN, DSpark) beat generic ones.
Nothing in this chapter has been measured in this repository. The DeepSeek V4 MTP run is
prepared in [tracks/nvidia-dynamo/studies/planned/05](../tracks/nvidia-dynamo/studies/planned/05-deepseek-layout/), and the numbers quoted
here are vendor- and community-reported.

| What you get from this repository | What you still own |
| --- | --- |
| The method, the cost model, per-engine flags, a turn-it-on checklist, and an MTP configuration prepared in [tracks/nvidia-dynamo/studies/planned/05](../tracks/nvidia-dynamo/studies/planned/05-deepseek-layout/) | Acceptance length measured on **your** prompts, at **your** temperature and concurrency |

## How it works

A decode step on a large model reads every active weight from HBM to produce one token per
sequence. At small batch the GPU is waiting on memory, not compute, so scoring 8 tokens costs
about the same as scoring 1. Speculative decoding exploits that spare compute:

1. A **drafter** proposes *k* tokens.
2. The **target** model scores all *k* (+1) positions in one forward pass.
3. Rejection sampling keeps the longest prefix consistent with the target's distribution and
   adds one target-generated bonus token. The output distribution is **identical** to
   ordinary decoding. This is a lossless optimization, not an approximation.

```text
Per-token acceptance probability α, k drafted tokens:
  expected tokens per verify step   E = (1 − α^(k+1)) / (1 − α)
  speedup ≈ E × T_step / (T_verify(k+1) + T_draft)

  α = 0.6, k = 7  →  E ≈ 2.5      (open-ended chat)
  α = 0.8, k = 7  →  E ≈ 4.2      (code, agents, math)
  α = 0.9, k = 7  →  E ≈ 5.7      (code edits, copy-heavy output)
```

Consistency check against published numbers (arithmetic, not a measurement): with E ≈ 4.2 and
verify plus draft costing about 1.3 ordinary steps at batch 1, the speedup is about 3.2×.
vLLM reports 3.14× for Kimi K3 with DSpark at batch 1 (118 → 370 tok/s on 16 GB300 GPUs,
[vLLM K3 post](https://vllm.ai/blog/2026-07-27-k3)).

## Why the gain disappears at high concurrency

At batch *B* the verify step processes *B × (k+1)* tokens. Once that number passes the GPU's
memory-bound/compute-bound crossover, verification costs real compute, and each rejected
draft token is wasted FLOPs that other sequences could have used. For dense FP8 weights on
Hopper the crossover is on the order of a hundred to a few hundred tokens per step. MoE moves
it, because each expert sees only a share of the batch. With *k* = 7, a batch of 32 already
puts 256 tokens in each step.

The published K3 recipe makes this concrete. vLLM's MI355X lane for Kimi K3 sizes the draft
length by concurrency, then switches the draft off
([vLLM K3 recipe](https://recipes.vllm.ai/moonshotai/Kimi-K3)):

| Concurrency per decode instance | 1 | 4 | 8–10 | 12–14 | 44+ |
|---|---|---|---|---|---|
| Draft tokens (DSpark) | 7 | 5 | 4 | 3 | off |

SGLang takes the adaptive route instead: DSpark's confidence head trims the verify window as
server load rises ([LMSYS K3 post](https://www.lmsys.org/blog/2026-07-27-kimi-k3-day0-support/)).
Either way, **the right *k* is a function of load**, and a static *k* tuned at batch 1
loses throughput at peak.

## Drafting methods

| Method | Drafter | Strengths | Costs and limits | Typical use |
|---|---|---|---|---|
| **n-gram / prompt lookup** | Token matches in the prompt and earlier output | No model, no memory, no training | Accepts well only when the output copies the input | Code edits, RAG answers quoting sources, agents echoing tool output |
| **Suffix decoding** | Suffix trees over the prompt and previous outputs | Adapts to repetitive agent loops across requests | Engine-specific; little help on novel text | Agent loops, repeated structured output |
| **Draft model** | A small model with the same tokenizer | Works for any target | Its own weights and KV; drafts sequentially; acceptance depends on how closely it matches the target | Dense families with a small sibling |
| **EAGLE / EAGLE-3** | One or a few layers fed by the target's hidden states | High acceptance for its cost; tree drafting at batch 1 | Must be trained per target; drafts sequentially | Most popular open models (community heads) |
| **MTP / NextN** | Multi-token-prediction heads trained **with** the model | Best-aligned drafts at near-zero extra weight; ships in the checkpoint | Only for models trained with MTP (DeepSeek V3/V4 and others) | Default when the checkpoint has it |
| **Block-parallel (DFlash, DSpark)** | A small non-causal model that drafts a whole block in **one** pass, plus a Markov head for intra-block dependency and a confidence head | Draft cost does not grow with *k*; long blocks stay cheap; confidence enables load-adaptive trimming | Model-specific; newest engine support | Kimi K3 (`Inferact/Kimi-K3-DSpark`, `RadixArk/Kimi-K3-DSpark`) |

**Rule:** if the checkpoint ships a native drafter (MTP, NextN or an official DSpark/EAGLE
head), start there. Use n-gram for copy-heavy traffic, where it costs nothing. Fall back to
a generic draft model only when nothing else exists.

## Acceptance depends on the workload

Acceptance is a property of the **traffic**, not of the model alone. Published K3 DSpark
acceptance lengths (draft block 7,
[RadixArk DSpark card](https://huggingface.co/RadixArk/Kimi-K3-DSpark),
[vLLM K3 post](https://vllm.ai/blog/2026-07-27-k3)):

| Workload (dataset) | Accepted tokens per step |
|---|---|
| Code generation (HumanEval, MBPP) | 5.5, 5.2 |
| Agentic coding (SWE-Rebench) | 4.7 |
| Math word problems (GSM8K) | 5.4 |
| Long context retrieval (RULER 1M) | 4.3 |
| Multi-turn chat (MT-Bench) | 3.9 |
| Hard reasoning (AIME 26) | 3.0 |
| Creative writing | 2.6 |

What pushes acceptance up: low temperature, structured or formulaic output (JSON, tool
calls, code, diffs), output that copies the input, and long outputs that settle into a
pattern. What pushes it down: high temperature, creative text, short outputs, and topics far
from the draft's training data.

## Speculative decoding with disaggregation

Speculation runs on the **decode pool**. It interacts with P/D in four ways:

1. **The handoff carries more.** EAGLE, MTP and DSpark need the draft's own prompt state
   (hidden states or a draft KV cache) on the decode worker. The prefill worker builds it and
   the transfer carries it, or decode rebuilds it. Support for each combination of
   algorithm, transfer backend and parallel layout is engine- and version-specific. SGLang
   added PP prefill with DCP decode and DSpark for K3 in a dedicated change
   ([sgl-project/sglang#40045](https://github.com/sgl-project/sglang/pull/40045)). vLLM had to
   split the DSpark draft out of the target's MLA KV group
   ([vllm-project/vllm#56952](https://github.com/vllm-project/vllm/pull/56952)). Treat every
   combination as unvalidated until the decode pool reports accepted tokens.
2. **It changes the P:D ratio.** By Little's law, decode sequences in flight are
   `λ × OSL × TPOT` ([chapter 09](09-parallelism-and-sizing.md)). Halving TPOT halves the
   sequences decode must hold, so the same traffic needs fewer decode GPUs and the ratio
   shifts toward prefill. Re-derive P:D after enabling speculation.
3. **It costs decode memory.** Draft weights (DSpark for K3 is about 2B parameters in BF16,
   about 4 GB) and draft KV come out of the decode KV budget, lowering *Sd*.
4. **Hybrid and linear-attention models need state rollback.** A rejected draft must restore
   the recurrent state (Mamba, KDA) to the last accepted position. Engines keep per-position
   snapshots. SGLang reduced this draft-state memory for K3 from 512 KB to 16 KB with
   ReplaySSM ([LMSYS K3 post](https://www.lmsys.org/blog/2026-07-27-kimi-k3-day0-support/)).
   Check that your engine supports speculation for the hybrid family at all before planning
   on it.

Aggregated serving gets the same per-token gains with none of the handoff complications. In
aggregated batches, though, prefill chunks still share each step with verification, so
speculation does not remove prefill-induced stalls.

## Engine configuration

Flag names as of the pinned or recipe versions in [reference/sources.md](../reference/sources.md);
verify against the image you deploy.

| Engine | Enable | Key knobs |
|---|---|---|
| **SGLang** | `--speculative-algorithm EAGLE \| EAGLE3 \| NEXTN \| DSPARK \| NGRAM` | `--speculative-num-steps`, `--speculative-eagle-topk` (1 = chain, > 1 = tree), `--speculative-num-draft-tokens`, `--speculative-draft-model-path`, `--speculative-dspark-block-size`. DeepSeek V4 in 0.5.16 accepts only `EAGLE` with topk 1 (the NextN head) or `DSPARK` ([engine flags](../reference/engine-flags.md#speculative-decoding-mtp-for-deepseek-v4)). |
| **vLLM** | `--speculative-config '{"method": "...", ...}'` with `mtp`, `eagle3`, `ngram`, `dspark` or a draft `model` | `num_speculative_tokens`; `prompt_lookup_min/max` for n-gram. The Dynamo K3 recipe uses `{"method": "dspark", "model": "Inferact/Kimi-K3-DSpark", "num_speculative_tokens": 7}` ([recipe](https://github.com/ai-dynamo/dynamo/blob/6822babc5c542350127e490f4fb8f2042855559c/recipes/kimi-k3/vllm/disagg-gb300-agentic/deploy.yaml)). |
| **TensorRT-LLM** | `speculative_config` in the LLM API options: MTP, EAGLE-3, n-gram, draft-target | Number of MTP or draft layers. Its optional relaxed acceptance for thinking tokens is **not** lossless; record it as a separate configuration. |

The repository's Kimi K3 profile keeps speculation **off** for first bring-up on B300
([reference/models.md](../reference/models.md#compatibility-limits)). Turning it on is a separate,
measured step.

## Measuring it honestly

| Pitfall | Effect | Do instead |
|---|---|---|
| Random-token or lorem-ipsum prompts | Acceptance near zero; understates the gain | Real or realistic text from your domain |
| Forced output length (`ignore_eos`, as this repository's load generators use) | After the natural end the model often repeats itself, which drafts predict easily; acceptance is inflated | Report acceptance separately on natural-length runs; keep forced lengths for capacity tests |
| Greedy decoding when production samples at T = 0.7 | Overstates acceptance | Benchmark at the production temperature |
| Synthetic acceptance (`synthetic_acceptance_length` in the Dynamo K3 recipe) | Useful for capacity planning; says nothing about real acceptance | Label it; never mix it with measured results |
| Reporting only batch-1 tokens/s | Hides the throughput loss at peak | Goodput at SLO across concurrency 1 → peak, speculation on and off |

Record the acceptance metrics with every run: SGLang `sglang:spec_accept_length` and
`sglang:spec_num_draft_tokens` (already in
[tracks/nvidia-dynamo/observability](../tracks/nvidia-dynamo/observability/metrics-inventory.txt)); vLLM
`vllm:spec_decode_num_accepted_tokens`, `vllm:spec_decode_num_draft_tokens` and
`vllm:spec_decode_num_drafts`. Alert when acceptance drops: it is the first sign of a traffic
shift or a draft/target mismatch after an upgrade.

## Turn it on when

| Condition | Speculation |
|---|---|
| Interactive traffic where per-user tokens/s matters, ≤ ~16–32 sequences per decode instance | **On** |
| Code, agents, tool calls, JSON, math: acceptance ≥ ~3.5 | **On**, longer drafts |
| Long outputs (reasoning, code generation) | **On**: most of the request time is decode |
| Checkpoint ships MTP / NextN / an official drafter | **On**: start there |
| Peak-throughput batch jobs at full batch | **Off**, or adaptive *k* |
| Creative or high-temperature chat (acceptance ≤ ~2.5) | Measure; often marginal |
| Very short outputs (< ~50 tokens: classification, FIM completion) | **Off**: little decode to speed up; n-gram at most |
| KV memory is the binding limit (very long contexts at high concurrency) | Measure: draft memory lowers *Sd* |

---

**Next:** [14 · What makes frontier MoE models fast](14-frontier-moe-techniques.md)
