# Engine flag review

[Home](../README.md) › [Reference](README.md) › Engine flags

**Executive summary.** Every non-default SGLang flag in the measured H200 configurations,
why it is set, what it costs, and the experiment that measures the alternative. Flag
behaviour is cited from SGLang v0.5.16 and Dynamo v1.4.0 sources
([upstream-verification.md](upstream-verification.md)). "Cost" is design reasoning unless
it cites `tracks/nvidia-dynamo/studies/`.

| Flag (as measured) | Why | What it costs | Alternative to measure |
| --- | --- | --- | --- |
| `--disable-overlap-schedule` (Nemotron 3 Nano) | With the radix cache on, the measured `--mamba-radix-cache-strategy no_buffer` forces overlap scheduling off for hybrid Mamba models (`arg_groups/overrides.py` L1158-1201; validated at `server_args.py` L4822-4829). It is set explicitly so the record is unambiguous. | The CPU scheduler no longer overlaps with GPU execution, which adds host time to every decode step. Not yet measured. | `extra_buffer` allows overlap for NemotronH with the triton linear-attention backend, at the cost of extra Mamba state memory: [tracks/nvidia-dynamo/studies/planned/06](../tracks/nvidia-dynamo/studies/planned/06-overlap-scheduling/) |
| `--mamba-radix-cache-strategy no_buffer`, `--page-size 1` | `no_buffer` requires page size 1 (`server_args.py` L4822-4829). It was the configuration that served correctly in both topologies, including Mamba-state transfer over NIXL. | Page size 1 means one KV-router block per token; the router's active-request weight is scaled to match (8000 ≈ one 8K prompt). | Same experiment 06 |
| `--moe-runner-backend marlin` (DeepSeek V4 Pro) | Upstream 1.4.0 recipes run V4 Pro on Blackwell with `flashinfer_mxfp4`, which indicates MXFP4 expert weights. Hopper has no FP4 tensor cores, so on H200 Marlin dequantizes them in the GEMM. A "native FP8 MoE path" does not apply to MXFP4 experts. | Dequantization overhead per expert GEMM. | SGLang 0.5.16 also lists `triton_kernel` and other MXFP4-capable backends; their Hopper support for V4 is `TODO(verify-upstream)`: [tracks/nvidia-dynamo/studies/planned/05](../tracks/nvidia-dynamo/studies/planned/05-deepseek-layout/) |
| `--kv-cache-dtype fp8_e4m3` (DeepSeek), `auto` (Nemotron) | FP8 KV halves KV memory for the 256K contexts. Nemotron keeps native BF16 KV; it has only 6 attention layers (about 6 KB of KV per token), so KV is not its limit. | FP8 KV quantization error (not quality-scored here). | — |
| `--cuda-graph-max-bs-decode` = `--max-running-requests` (136 for TP4, 4 for TP8) | Decode batches larger than the largest captured CUDA graph run eagerly. Matching the two keeps every decode step on a graph. | Capture time and memory grow with the cap. | Keep them equal when changing either |
| `--disable-cuda-graph` (prefill role) | Prefill batches vary widely in token count; graphs give little benefit and cost memory. | None measured. | — |
| `--chunked-prefill-size 4096` | The same value in every study, to keep topologies comparable. A 128K prompt takes 32 chunks. | Many scheduler iterations per long prompt (TTFT). In aggregated mode each chunk delays every running stream. | 8192 and 16384 at 128K: [tracks/nvidia-dynamo/studies/planned/07](../tracks/nvidia-dynamo/studies/planned/07-prefill-chunk-size/) |
| `--mem-fraction-static 0.88` | Leaves headroom for activations and CUDA graphs; the KV pool is sized automatically (19.6M tokens per TP4 Nemotron worker). | — | — |
| `--max-running-requests 136` decode / `32` prefill (operator graphs) | Decode: 128 per worker on average plus headroom, because a cap of 128 queued router overflow in the 8K/128K study. Prefill: bounds the requests holding transfer staging memory (prefill host memory peaked at 308 GiB at 136). | A lower prefill cap can queue bursts on the prefill pool (TTFT). | [tracks/nvidia-dynamo/studies/planned/04](../tracks/nvidia-dynamo/studies/planned/04-reliability/) |
| `--gc-threshold 7000 10 100` (operator graphs) | Generation-2 Python GC paused output for 0.34–0.45 s about every 11 s per worker. Higher thresholds make full collections ~100× rarer. | Higher steady-state Python heap. | Default thresholds against this value, plus `gc.freeze()` after warmup: experiment 04 |
| `--tensor-parallel-size 8` (128K and 256K studies) | Matched the 16-GPU, two-worker comparison. For Nemotron 3 Nano this is not a sizing recommendation: the 30B-A3B weights fit on one GPU. | All-reduce on every layer across 8 GPUs; only two workers to split between prefill and decode. | TP2/TP4 workers: [tracks/nvidia-dynamo/studies/planned/01](../tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/) |

## Speculative decoding (MTP) for DeepSeek V4

SGLang 0.5.16 accepts only `EAGLE` (with `--speculative-eagle-topk 1`) or `DSPARK` as the
speculative algorithm for DeepSeek V4 (`arg_groups/deepseek_v4_hook.py`). It ships a
`deepseek_v4_nextn` draft model, so MTP means `--speculative-algorithm EAGLE
--speculative-eagle-topk 1`, using the checkpoint's NextN head. MTP mainly lowers TPOT at
low to moderate concurrency, a decode-side lever. It has not been run here
(tracks/nvidia-dynamo/studies/planned/05).

## Speculative decoding (DSpark) for Kimi K3

Published, not run here. NVIDIA's Dynamo K3 recipe enables DSpark on vLLM with
`--speculative-config '{"method":"dspark","model":"Inferact/Kimi-K3-DSpark","num_speculative_tokens":7}'`.
SGLang uses `--speculative-algorithm DSPARK --speculative-draft-model-path RadixArk/Kimi-K3-DSpark
--speculative-dspark-block-size 7`. The repository's `kimi-k3` profile keeps speculation off
for first bring-up. Reduce the draft length as decode concurrency rises
([chapter 13](../blueprint/13-speculative-decoding.md#why-the-gain-disappears-at-high-concurrency)).
