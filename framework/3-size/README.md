# 3 · Size: GPUs, workers, replicas and KV

[Home](../../README.md) › [Framework](../README.md) › 3 · Size

**Output:** a sizing sheet (table below) attached to the design record. **Gate:** weights and
KV fit per worker with the engine's own numbers, and replica counts come from throughput
measured at the SLO on the target hardware. Background: [blueprint 09](../../blueprint/09-parallelism-and-sizing.md),
[08](../../blueprint/08-kv-cache-and-offloading.md), [15 §1](../../blueprint/15-workload-driven-design.md#1-the-prefill-to-decode-work-ratio).

## Steps

1. **Minimum worker.** GPUs per worker ≥ weights ÷ (HBM per GPU × usable fraction). Leave
   room for KV and activations; a worker that only just fits the weights serves almost
   nothing.
2. **KV capacity per worker.** Start from the engine's report after load (vLLM logs
   `GPU KV cache size: N tokens`; SGLang logs `max_total_num_tokens`). Model-side estimates
   from KV bytes per token are for planning only.
3. **Concurrency per worker at the target context.** KV tokens ÷ (ISL + OSL) for distinct
   sessions; prefix reuse lets more requests share blocks.
4. **Throughput per worker at the SLO.** Calibrate cold prefill tokens/s at the real ISL and
   decode tokens/s at the planned batch; for SLA goals, run a short goodput sweep instead.
5. **Replicas.** Peak demand ÷ per-worker capacity at the SLO, plus failure headroom (N+1).
6. **P:D ratio** (only if D1 chose P/D). Compute *R* with routing and speculation in their
   production state; check the fleet has at least 1 + max(*R*, 1/*R*) workers.
7. **Reuse working set.** Active sessions × reusable context. If it exceeds the aggregate KV
   of the workers that will hold it, plan KV tiering or more replicas; routing alone cannot help.
8. **Cold start.** Weights ÷ storage read throughput, plus engine warmup. It bounds how fast
   autoscaling can add capacity and how long a failed node takes to recover.

## Sizing sheet

| Quantity | Formula or source | Value |
| --- | --- | --- |
| Weights per replica | Checkpoint size | |
| GPUs per worker (minimum, chosen) | Step 1 | |
| KV tokens per worker | Engine log after load | |
| Sessions per worker at target context | Step 3 | |
| Prefill tokens/s at ISL, decode tokens/s at batch | Calibration | |
| Replicas (and P:D) | Steps 5–6 | |
| Reuse working set vs aggregate KV | Step 7 | |
| Cold start per replica | Step 8 | |

## Worked example: DeepSeek V4 Pro 0813 on H200

| Quantity | Value | Note |
| --- | --- | --- |
| Weights | 893 GB | MXFP4 experts + FP8 |
| GPUs per worker | 8 × H200 (1,128 GB) | 4 × H200 (564 GB) cannot hold the weights |
| Replicas | 4, one per node | Each needs its own RWO weight disk |
| Cold start | ≈ 35 min per replica | 893 GB at ~400 MB/s per network SSD, read in parallel on each node |
| KV tokens, prefill tokens/s | Measured in the [routing study](../../tracks/llm-d-redhat/studies/deepseek-v4-pro-256k-routing/README.md) | |

---

**Next:** [4 · Deploy and validate](../4-validate/README.md)
