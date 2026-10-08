# 15 · Workload-driven design: model, traffic and the advanced methods

[Home](../README.md) › [Blueprint](README.md) › 15 · Workload-driven design

**Executive summary.** Three numbers decide most of the design: the **prefill-to-decode work
ratio** *R*, the **transfer intensity** of the model (KV bytes moved per unit of prefill
compute), and the **tightness of the ITL SLO**. Disaggregation pays when *R* is between about
0.15 and 7, so both pools are substantial. It also needs enough workers to express *R* as an
integer split, a model whose KV is cheap to move (large MoE, MLA, hybrid), a tight p99 ITL
target and RDMA. Outside that window, aggregated replicas with KV-aware routing win. All three
H200 studies fell outside it, and aggregated won all three
([chapter 12](12-results-and-reconciliation.md)). Workload type then decides which advanced
methods are worth turning on. Code and agents favour speculative decoding and deep prefix
caching; RAG favours prefill-side levers; reasoning is a decode problem.

| What you get from this repository | What you still own |
| --- | --- |
| The ratio rule, model and workload matrices, a method-by-workload table, and worked examples tied to the measured studies | Your ISL/OSL/reuse distributions, measured *Tp* and *Sd*, and your SLOs |

The constants in this chapter (*Tp*, *Sd*, typical ISL/OSL) are **illustrative**. They show how
the decision moves, not where your boundary is. Measure your own with
[benchmarks/](../benchmarks/README.md) and [tracks/nvidia-dynamo/studies/planned/01](../tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/).

## 1. The prefill-to-decode work ratio

From the pool-sizing formulas in [chapter 09](09-parallelism-and-sizing.md):

```text
N_P = λ × ISL × (1 − r) / Tp            prefill workers
N_D = λ × OSL × TPOT   / Sd             decode workers (Little's law)

R   = N_P / N_D = [ ISL × (1 − r) / OSL ] × [ Sd / (Tp × TPOT) ]
                  └── the workload ──┘    └── the model on its hardware ──┘
```

*R* is the P:D ratio the traffic needs. Arrival rate cancels, so *R* depends only on the
**shape** of the traffic and the per-worker capacities. Three things move it:

| Change | Effect on *R* |
|---|---|
| Longer inputs, shorter outputs | Up (toward prefill) |
| More prefix reuse *r* (KV-aware routing, multi-turn, agents) | **Down, sharply:** going from r = 0 to r = 0.9 divides prefill work by 10 |
| Speculative decoding (lower TPOT) | Up: decode holds fewer sequences ([chapter 13](13-speculative-decoding.md)) |
| Tighter ITL target (lower TPOT and lower *Sd*) | Usually up per decode worker; measure |

### The disaggregation window

| *R* | What it means | Topology |
|---|---|---|
| < ~0.15 | Decode-dominated: prefills are rare and short relative to decode | Aggregated. Exception: a strict tail-ITL SLO (see below) |
| ~0.15 – ~7 | Both phases are substantial | **Candidate** for disaggregation, if the other conditions hold |
| > ~7 | Prefill-dominated: few streams are decoding, so there is little to protect | Aggregated with larger prefill chunks and context parallelism |

**Minimum workers to express *R*.** With *N* workers the ratio moves in steps of one worker,
and the smaller pool needs at least one. A useful floor:

```text
N_min ≈ 1 + max(R, 1/R)        R = 0.2 → 6 workers (1P:5D);   R = 4 → 5 workers (4P:1D)
```

Below *N_min* the split is forced and capacity is stranded. At R = 0.2 on two workers (1P:1D),
the decode pool has 50% of the GPUs where it needs 83%. Throughput is capped near 60% of a
balanced split, which is the H200 site's situation. Plan for about 2 × *N_min* so the Planner
has room to follow the traffic. On 8-GPU nodes, this is the reason to use TP1–TP4 workers for
models that fit.

**The tail-latency exception.** A decode-dominated workload with a strict p99.9 or worst-case
ITL target can still justify a small prefill pool. In the H200 8K-in/128K-out study,
aggregated serving had 34% more throughput but a 40.4 s worst inter-token gap, against 1.1 s
disaggregated ([chapter 12](12-results-and-reconciliation.md)). Buy the tail only when the SLO
requires it.

## 2. Transfer intensity: which models are cheap to disaggregate

P/D moves the prompt's KV once per request. What matters is how big that payload is
**relative to the prefill compute it saves**. Prefill compute per token is about 2 × active
parameters (attention FLOPs, which grow with context, are ignored here):

| Model (KV dtype) | KV per token | Prefill GFLOP per token | KV per GFLOP | Relative |
|---|---|---|---|---|
| Llama 3 8B dense, GQA (BF16) | 128 KiB | 16 | ~8 KB | 60× |
| Llama 3 70B dense, GQA (FP8) | 160 KiB | 140 | ~1.2 KB | 9× |
| Nemotron 3 Nano 30B-A3B hybrid (BF16) | ~6 KB (6 of 52 layers attend) | 6 | ~1 KB | 8× |
| DeepSeek V3-class MLA MoE (FP8) | ~35 KB | 74 | ~0.47 KB | 3.5× |
| Kimi K3, KDA + MLA (FP8, reported) | ~27 KB + fixed KDA state | 208 | ~0.13 KB | 1× |

KV sizes are computed from published configurations (K3 as reported by SGLang). Small dense
models move about 60× more bytes per unit of saved compute than K3. Their prefill is short, so
the handoff is a large fraction of TTFT. **Large MoE with MLA or hybrid attention is where
disaggregation is cheapest**, and also where per-phase parallelism (DP attention, wide EP, PP
prefill) gains the most ([chapter 14](14-frontier-moe-techniques.md)).

## 3. Model type and size

| Model class | Typical worker | Default topology | When to disaggregate | Speculative decoding | Other levers |
|---|---|---|---|---|---|
| **Small dense ≤ ~15B** | TP1, many replicas | Aggregated + KV router | Rarely: high transfer intensity, short prefills | EAGLE-3 or n-gram; small draft models are a poor fit (the target is already small) | Prefix caching, FP8 |
| **Mid dense 30–70B** | TP2–TP4 (H200), TP1–TP2 (B300, FP8/FP4) | Aggregated | Long inputs (≥ 16K effective), tight ITL, RDMA; FP8 KV to halve the payload | EAGLE-3 or a same-family draft (e.g. a 1–3B sibling) | FP8 KV, chunked prefill tuning |
| **Small MoE (30B-A3B class)** | TP1–TP4 | Aggregated (measured on H200) | Only with TP2/TP4 workers so P:D is tunable ([tracks/nvidia-dynamo/studies/planned/01](../tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/)) | MTP if shipped; EAGLE-3 | Many small workers; KV router |
| **Large MoE 200–500B** (Qwen3 235B/480B) | One node, TP8/EP8 | Aggregated on 1–2 nodes; P/D from about 4 nodes | When prefill wants small TP and decode wants wide EP | EAGLE-3 / MTP where available | EP, FP8, DP attention if supported |
| **Frontier MoE + MLA ≥ 600B** (DeepSeek V4, Kimi K2/K3) | 1 node (B300) to a rack (NVL72) | P/D at scale; aggregated TP8 for small deployments and bring-up | Default at scale: low transfer intensity, phase-specific layouts | **Native MTP/NextN/DSpark**: the biggest single per-user gain | DP attention, wide EP, DCP, FP4 on Blackwell |
| **Hybrid SSM / linear attention** (Nemotron 3, Qwen3-Next, K3) | Per size class above | Per size class | Payload includes SSM/KDA state; small at long context | Only if the engine supports state rollback for the family | Snapshot-aware prefix caching ([chapter 08](08-kv-cache-and-offloading.md)) |
| **Multimodal** | Text backbone + encoder | Per backbone | E/P/D when encoders are heavy ([chapter 03](03-disaggregation-pattern.md)) | Per backbone | Media caching |

## 4. Workload types

Typical shapes, used to compute *R* with the illustrative constants *Tp* = 40,000 tokens/s and
*Sd* = 64 sequences at TPOT 30 ms, which give *R* ≈ ISL × (1 − r) / (18.75 × OSL):

| Workload | ISL | OSL | Reuse *r* | SLO that binds | *R* | Leans |
|---|---|---|---|---|---|---|
| **Chatbot** (multi-turn) | 1–8K (3K) | 200–800 (400) | 0.3–0.7 (0.5) | TTFT < 1 s, ITL ≤ 50 ms (reading speed) | 0.2 → 1:5 | Aggregated on small fleets; P/D from about 6+ workers with tight ITL |
| **RAG / document QA** | 8–128K (32K) | 200–1K (400) | 0–0.3 (0.1) | TTFT | 3.8 → 4:1 | Prefill-heavy. P/D if ITL is tight and N ≥ 5; otherwise aggregated with large chunks |
| **Agent tool loop** (per turn) | 20–200K, growing (60K) | 50–500 (300) | **0.8–0.95** (0.9) | Per-turn TTFT; task completion time | 1.1 → 1:1 (at r = 0: 11:1) | Reuse decides everything. KV routing first; P/D at scale |
| **Agentic coding** | 30–200K (80K) | 1–8K (2K) | 0.7–0.9 (0.85) | Task time; per-user tok/s | 0.32 → 1:3 | P/D at scale; speculation strongly on |
| **Reasoning / thinking** | 1–4K (2K) | 8–64K (16K) | 0.2–0.5 (0.3) | Per-user tok/s, total time | 0.005 → 1:200 | Aggregated (decode-dominated); speculation on |
| **Code completion (FIM)** | 2–8K (4K) | 10–100 (40) | 0.5–0.8 (0.6) | TTFT p99 < ~300 ms | 2.1 → 2:1 | Aggregated: requests too small to amortize a handoff, and too short for ITL stalls |
| **Batch / offline** (summarize, extract, evaluate) | 4–32K (16K) | 200–1K (500) | ~0 | Throughput, cost per token | 1.7 | Aggregated, maximum batch: no ITL SLO to protect |

Worked numbers are in the *R* column; ranges are typical, and the values in parentheses are the
ones used. The measured H200 studies fall at the edges. The 256K-input study (R ≫ 7) and the
128K-in/256-out study (R ≈ 27 with these constants) are prefill-dominated. The 8K-in/128K-out
study (R ≈ 0.003) is decode-dominated. Aggregated won all three, as the window predicts.

### What each workload does to memory

| Workload | KV pressure | Implication |
|---|---|---|
| Chatbot | Moderate; history grows per turn | KV tiering to host DRAM for idle sessions ([chapter 08](08-kv-cache-and-offloading.md)) |
| RAG | High per request, low reuse | FP8 KV; context parallel prefill at ≥ 128K |
| Agents and coding | Very high, **long-lived** across turns and think-time | Prefix cache plus offload tiers are mandatory at scale; route turns to the worker that holds the prefix |
| Reasoning | KV grows **during decode** to tens of thousands of tokens | Decode KV capacity limits concurrency: DCP or DP attention for MLA, FP8 KV |
| Batch | Large but transient | Maximize batch; no tiering needed |

## 5. Which advanced methods, for which workload

● turn on · ◐ conditional (see the right-hand column) · ○ little benefit or harmful

| Method | Chat | RAG | Agent loop | Agentic coding | Reasoning | FIM | Batch | Turn on when |
|---|---|---|---|---|---|---|---|---|
| KV-aware routing | ● | ● | ● | ● | ◐ | ● | ◐ | More than one worker and any prefix reuse |
| Prefix caching | ● | ◐ | ● | ● | ◐ | ● | ◐ | Shared system prompts, multi-turn, repeated documents |
| KV offload tiers (host, NVMe, shared) | ◐ | ◐ | ● | ● | ○ | ◐ | ○ | The reusable working set exceeds HBM ([chapter 08](08-kv-cache-and-offloading.md)) |
| **P/D disaggregation** | ◐ | ◐ | ◐ | ◐ | ○ | ○ | ○ | 0.15 ≲ R ≲ 7, N ≥ N_min, tight ITL, RDMA, low transfer intensity |
| **Speculative decoding** | ◐ | ◐ n-gram | ● | ● | ● | ○ | ○ | Acceptance ≥ ~3, ≤ ~16–32 sequences per decode instance ([chapter 13](13-speculative-decoding.md)) |
| Larger prefill chunks (8–16K) | ○ | ● | ● | ● | ○ | ○ | ● | Long ISL and no tight ITL in aggregated mode, or any long ISL on a prefill pool ([tracks/nvidia-dynamo/studies/planned/07](../tracks/nvidia-dynamo/studies/planned/07-prefill-chunk-size/)) |
| Context / pipeline parallel prefill | ○ | ● | ◐ | ◐ | ○ | ○ | ◐ | ISL ≥ ~128K where single-worker TTFT misses the SLO |
| DCP / DP attention on decode | ○ | ◐ | ● | ● | ● | ○ | ◐ | MLA models whose decode KV capacity limits concurrency |
| Wide EP on decode | ◐ | ◐ | ◐ | ◐ | ◐ | ○ | ● | Large MoE at high decode concurrency, ideally inside NVLink |
| FP8 KV cache | ◐ | ● | ● | ● | ● | ○ | ● | KV-bound; quality checked on your evals |
| FP4 weights (NVFP4/MXFP4) | ● | ● | ● | ● | ● | ● | ● | Blackwell or newer and a checkpoint trained or calibrated for it |
| Structured output / tool-call grammar | ○ | ○ | ● | ● | ○ | ○ | ◐ | Tool calls or JSON contracts; validate parsers per engine |
| SLO-driven autoscaling (Planner) | ● | ◐ | ● | ● | ◐ | ● | ○ | Diurnal or bursty traffic with latency SLOs; batch uses queue depth instead |

### How the methods interact

- **Prefix reuse and P/D compete for the same prize.** A 90% cache hit removes 90% of prefill,
  which can move a workload out of the disaggregation window entirely. Enable and measure
  KV-aware routing **before** deciding on P/D ([tracks/nvidia-dynamo/studies/planned/02](../tracks/nvidia-dynamo/studies/planned/02-kv-router/)).
- **Speculation shifts P:D toward prefill**, and its draft memory lowers decode capacity.
  Size the pools with speculation in its production setting.
- **Speculation and wide EP pull in opposite directions.** Wide EP wants huge decode batches;
  speculation pays at small ones. Choose by SLO: interactivity or throughput
  ([chapter 14](14-frontier-moe-techniques.md#two-operating-points-not-one)).
- **Large prefill chunks in aggregated mode trade TTFT for ITL stalls.** On a dedicated
  prefill pool there is no such trade, so chunks can grow freely.

## 6. Putting it together

1. Characterize traffic per workload class: ISL, OSL, reuse *r*, arrival pattern, SLOs.
   Mixed fleets are often better served as **separate graphs per class** (for example, chat
   and coding on different pools) than as one compromise.
2. Compute *R* from measured *Tp* and *Sd*, with KV routing and speculation in their
   intended production state.
3. Check the window, *N_min*, transfer intensity, the ITL SLO and the fabric. If any fails,
   deploy aggregated replicas with KV-aware routing.
4. Turn on the methods marked ● for the workload, then the ◐ ones whose conditions hold.
5. Measure goodput at SLO for aggregated against your best P:D split, across concurrency
   ([benchmarks/](../benchmarks/README.md)). Keep the measured winner, not the predicted one.

---

**Back to:** [Blueprint index](README.md) · **Decide:** [chapter 11](11-decision-guide.md)
