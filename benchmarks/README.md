# Benchmarks: measuring and comparing deployments

[Home](../README.md) › Benchmarks

**Goal:** measure every track with the **same workload**, then compare aggregated with disaggregated and vLLM with SGLang, without fooling yourself.

**Contents**

1. [The comparison experiment](#1-the-comparison-experiment)
2. [Workloads and datasets](#2-workloads-and-datasets)
3. [Running one measurement](#3-running-one-measurement)
4. [Sweeps](#4-sweeps)
5. [Long context: more than 250K input tokens](#5-long-context-more-than-250k-input-tokens)
6. [Metrics](#6-metrics)
7. [Outputs and the comparison notebook](#7-outputs-and-the-comparison-notebook)
8. [Rules for a fair comparison](#8-rules-for-a-fair-comparison)

This folder holds the benchmark code and the methodology. Seed data lives in [datasets/](../datasets/), and the report in [benchmarks/compare.ipynb](compare.ipynb). Run modules from the repository root with `python -m benchmarks.<module>`.

| Module | Purpose |
|---|---|
| [generate_dataset.py](generate_dataset.py) | Expands the seed fixtures into deterministic, token-counted chatbot or agentic sessions |
| [run.py](run.py) | Streams sessions against an OpenAI-compatible endpoint and records TTFT, TPOT, ITL, throughput and failures per request |
| [metrics.py](metrics.py) | Metric definitions and summaries (unit-tested) |
| [collect.py](collect.py) | Rebuilds `tracks/nvidia-dynamo/studies/summary.csv` from all run folders |
| [loadgen.py](loadgen.py) | Open-loop (Poisson or constant RPS) or closed-loop sessions with sampled ISL/OSL; **goodput at SLO**, SLO attainment, cost per million tokens, AIPerf/genai-perf export |
| [sweep.py](sweep.py) | Sweeps RPS × P:D ratio × TP per role from a YAML spec and writes one `sweep-table.csv` |
| [distributions.py](distributions.py) | Seeded ISL/OSL distributions (`fixed`, `uniform`, `lognormal` clipped) |
| [driver_lock.py](driver_lock.py) | One driver per results directory; append-only cache-flush evidence |
| [long_decode.py](long_decode.py) | Forced long outputs (e.g. 128K tokens) at hundreds of concurrent streams: multi-process client, compact per-token intervals, client and server ITL, stall counts, `--reanalyze` |

---

## 1. The comparison experiment


1. Generate the dataset **once** (section 2).
2. Deploy one track from [tracks](../tracks/README.md), verify it (step 6 of its guide), run the sweep (section 4), then tear it down.
3. Repeat for the next track with **the same dataset file** and the same concurrency levels.
4. Run `python -m benchmarks.collect` and open the notebook.

| Question | Compare |
|---|---|
| Does disaggregation help this workload? | 01 aggregated vLLM against 02 Dynamo disaggregated vLLM |
| Does it help on SGLang? | 01 aggregated SGLang against 03 Dynamo disaggregated SGLang |
| Which engine is faster here? | 02 against 03 (or 01 vLLM against 01 SGLang). This is a **stack** comparison: engine, image and KV dtype all differ. |
| Dynamo against llm-d | 02 against [04](../tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/), same engine and model |

Every run records its `technology` and `backend` from the track's `deployment.json`, so the notebook keeps the cohorts apart.

| Technology label | Deployment |
|---|---|
| `dynamo-agg-compose`, `dynamo-agg-k8s` | 01 aggregated |
| `dynamo-disagg-compose`, `dynamo-disagg-k8s` | 02 and 03 disaggregated (backend tells them apart) |
| `llmd-k8s` | 04 llm-d |
| `dynamo-compose`, `dynamo-k8s` | Legacy labels from earlier versions of this repository (disaggregated) |

---

## 2. Workloads and datasets

`datasets/seeds/chatbot.jsonl` and `agentic.jsonl` are small, original, synthetic fixtures. The generator expands them into deterministic, token-counted sessions with unique prefixes:

- **chatbot:** three-turn conversations over a long shared context.
- **agentic:** three requests around recorded `read_file` / `run_tests` tool calls and results, preserving tool-call IDs and history.

This is **recorded workload replay**. Later turns use fixed recorded history, not the model's previous answer. It measures serving behavior under agent-like context growth and prefix reuse. It does not measure answer quality or tool-call accuracy, and no model-generated commands are executed. For production realism, supply redacted traces in the same format or pass `--corpus` with representative text.

Generate a dataset that fits the deployed 32K context:

```bash
python -m benchmarks.generate_dataset --workload chatbot --sessions 8 \
  --input-tokens 8000 --output-tokens 256 --max-model-len 32768 \
  --tokenizer /data/nemotron-ultra/model --trust-remote-code \
  --template-kwargs '{"enable_thinking":false,"force_nonempty_content":true}' \
  --out datasets/generated/nemotron-chatbot-8k.jsonl
```

The generator writes measured, template-inclusive `input_tokens` per turn, plus a `.meta.json` file with the seed, tokenizer and hash. The runner never silently truncates.

DeepSeek V4 checkpoints ship a Python message encoder instead of a Hugging Face
Jinja chat template. With a local copy of the pinned checkpoint's tokenizer and
`encoding/encoding_dsv4.py`, add
`--deepseek-v4-encoder /path/to/checkpoint/encoding/encoding_dsv4.py
--trust-remote-code --template-kwargs '{"thinking":false}'`. The generator uses
the official encoder for chat and tool histories and records its SHA256 in the
dataset metadata. See the [H200 deployment guide](../tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/)
for a complete download and benchmark example.

One JSONL row is a session:

```json
{"id":"unique-session-id","workload":"agentic","turns":[{"messages":[{"role":"user","content":"Investigate this incident."}],"input_tokens":8}]}
```

---

## 3. Running one measurement

```bash
python -m benchmarks.run \
  --base-url http://<B300_NODE_A_IP>:8000/v1 \
  --model nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4 \
  --technology dynamo-disagg-compose \
  --deployment tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/deployment.json \
  --dataset datasets/generated/nemotron-chatbot-8k.jsonl \
  --max-model-len 32768 --output-tokens 256 \
  --concurrency 4 --warmup 1 --timeout 3600 --cache-state uncontrolled \
  --metrics-url http://<B300_NODE_A_IP>:8081/metrics \
  --metrics-url http://<B300_NODE_B_IP>:8081/metrics
```

- `--deployment` must be the `deployment.json` of the track you deployed. The runner checks that `--technology`, `--model` and `--max-model-len` match it, and merges the model's request defaults (for example, disabling thinking for Nemotron).
- `--metrics-url` snapshots each worker's Prometheus metrics before and after the run.
- Run the client **in the private network**, on a host with enough CPU and RAM for large prompts. For Kubernetes use `http://<node-a-ip>:8000/v1` rather than a port-forward.
- Authentication, if you add it, is read from `BENCHMARK_API_KEY` and never saved.
- `--token-ids` requests vLLM's `return_token_ids` extension for exact per-token ITL. It is rejected for SGLang.

---

## 4. Sweeps

```bash
CONCURRENCIES='1 2 4 8' REPETITIONS=3 bash tools/sweep.sh \
  --base-url http://<B300_NODE_A_IP>:8000/v1 \
  --model nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4 \
  --technology dynamo-disagg-compose \
  --deployment tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/deployment.json \
  --dataset datasets/generated/nemotron-chatbot-8k.jsonl \
  --max-model-len 32768 --output-tokens 256
```

The sweep stops on errors or invalid measurements, so failures cannot disappear into an average. Collect all runs afterwards with `python -m benchmarks.collect`.

Closed-loop saturation is the default. `--session-rate 0.1` paces new sessions at 0.1 per second under the concurrency cap. `--think-time 1` inserts one second between turns.

---

## 5. Long context: more than 250K input tokens

For the DeepSeek V4 Pro H200 experiment, see the [256K comparison protocol](../tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/REPORT.md) and [dedicated notebook](../tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/deepseek_v4_pro_256k.ipynb). It uses the native encoder, in-cluster load generation and an acknowledged KV-cache reset before each topology run.

For Nemotron 3 Nano, the [128K protocol](../tracks/nvidia-dynamo/studies/nemotron-3-nano-128k-comparison/REPORT.md)
uses its native chat template, 32 sessions and three repeats per topology. Its
[notebook](../tracks/nvidia-dynamo/studies/nemotron-3-nano-128k-comparison/nemotron_3_nano_128k.ipynb) reports run means and ranges.

The reverse workload, 8K input and 128K forced output at maximum concurrency, uses
`benchmarks.long_decode`; see the [8K/128K protocol](../tracks/nvidia-dynamo/studies/nemotron-3-nano-8k-128k-comparison/REPORT.md).
Generate single-turn sessions with `generate_dataset --turns 1`.

1. **Redeploy with a larger window.** In the worker command of your track, set `--max-model-len 262144 --max-num-seqs 4` for vLLM, or `--context-length 262144 --max-running-requests 4` for SGLang. Update `max_model_len` in `deployment.json` to match. Restart **both** roles.
2. **Generate a matching dataset:**

   ```bash
   python -m benchmarks.generate_dataset --workload agentic --sessions 8 \
     --input-tokens 256000 --output-tokens 512 --max-model-len 262144 \
     --tokenizer /data/nemotron-ultra/model --trust-remote-code \
     --template-kwargs '{"enable_thinking":false,"force_nonempty_content":true}' \
     --out datasets/generated/nemotron-agentic-256k.jsonl
   ```

3. **Run** with `--max-model-len 262144 --min-input-tokens 250001 --output-tokens 512`. The runner verifies the real server-side token counts.

A 262,144-token input cannot also reserve output inside a 262,144-token window, so leave headroom for every turn. Increase context and concurrency step by step while watching GPU memory and transfer errors. For models whose tokenizer is not a standard Hugging Face tokenizer, see [reference/models.md](../reference/models.md).

---

## Realistic traffic: open-loop load, goodput and sweeps

The recorded H200 studies are closed-loop waves: 128K-token prompts at concurrency 4,
and 8K prompts with 131,072 forced output tokens. Both are extremes. Neither shows
where disaggregation pays off, and the fixed 1P:1D and 1P:3D layouts were structurally
unfavourable to it. `loadgen.py` and `sweep.py` measure the regime production runs in.

**Workload.** Generate sessions with sampled lengths (defaults below are the experiment
defaults; without the flags the generator output and hashes are unchanged):

```bash
python -m benchmarks.generate_dataset --workload chatbot --sessions 2000 --turns 1 \
  --isl-dist lognormal:4000:0.6:2000:16000 --osl-dist lognormal:512:0.6:256:2048 \
  --max-model-len 262144 --seed 20261002 --tokenizer build/nemotron-128k/tokenizer \
  --template-kwargs '{"enable_thinking":false}' --out datasets/generated/nemotron-realistic.jsonl
```

Keep all three recorded turns (omit `--turns 1`) for a **multi-turn prefix-reuse** mode,
and use a large fixed `--input-tokens` for a **long-context** mode.

**Arrivals.** `--arrival poisson --rps R` starts sessions at exponential inter-arrival
times (open loop: load does not back off when the server slows). `constant` uses even
spacing. `closed --concurrency N` reproduces the earlier studies' closed loop. The client
records each session's scheduled and actual start (`start_lag_ms`), so an overloaded
client is visible.

**Primary metric: goodput.** A request meets the SLO when its TTFT ≤ `--slo-ttft-ms` and
the p99 of its own inter-token intervals ≤ `--slo-itl-ms`. `goodput_rps` is the rate of such
requests. `slo_attainment` is their share of valid requests. `run_meets_slo` checks the run
as a whole: pooled p99 TTFT and p99 ITL within target. Report goodput next to tokens/s;
a configuration that delivers more tokens/s while missing the SLO has lower goodput.

**Cost.** With `--gpu-hour-usd`, the summary adds `usd_per_m_output_tokens` and
`usd_per_m_output_tokens_at_slo` (GPU-hours × price, divided by all output tokens or by
tokens from SLO-meeting requests). The price is blank by default; each site records its
own in its site configuration.

**Sweeps.** `python -m benchmarks.sweep plan|run <spec.yaml>` expands configurations
(overlay, P:D ratio, TP per role) × RPS levels, applies each configuration once, runs
`loadgen` at every RPS and holds the driver lock. `python -m benchmarks.sweep table <results>`
writes `sweep-table.csv` and marks each configuration's best RPS that still meets the SLO.

### Comparing with NVIDIA's published numbers (AIPerf / genai-perf)

Every `loadgen` run also writes `profile_export.json` with genai-perf/AIPerf metric names
and units. The definitions differ in two places:

| This repository | AIPerf / genai-perf | Relation |
| --- | --- | --- |
| `tpot_ms`: (last token − first token) / (output tokens − 1), per request | `inter_token_latency` (per-request average) | Same quantity; exported as `inter_token_latency` |
| `itl_ms_*`: every gap between streamed tokens, pooled over the run | not reported as a distribution | Exported as `inter_token_gap`; tail ITL (p99, p99.9) only exists here |
| `ttft_ms`: request start to first generated payload | `time_to_first_token` | Same |
| `output_throughput_tps`: valid output tokens ÷ wall time | `output_token_throughput` | Same, except failed and invalid requests are excluded here |
| `goodput_rps`: requests meeting TTFT and per-request p99 ITL targets | goodput with user-defined constraints (varies by version) | Compare only with identical constraints |

Published Dynamo results usually use concurrency-driven AIPerf runs with fixed ISL/OSL.
Use `--arrival closed --concurrency N` and `fixed:` distributions to match such a setup
before comparing numbers.

## 6. Metrics

| Column | Definition |
|---|---|
| `ttft_ms` | Request start to first generated payload (content, reasoning, tool-call payload or explicit token ID). Role-only and empty deltas are excluded. |
| `first_content_ms` | Request start to first visible text. May follow reasoning, or be absent for a tool-only response. |
| `e2e_ms` | Request start to stream completion or error |
| `tpot_ms` | `(last output arrival − first output arrival) / (completion_tokens − 1)` |
| `output_tps` | Per-request completion tokens divided by end-to-end seconds |
| `decode_tps` | `(completion_tokens − 1) / output-arrival span`, the reciprocal of TPOT |
| `output_throughput_tps` | Valid successful output tokens divided by experiment wall time |
| `input_throughput_tps` | Valid input tokens divided by wall time. Includes cached input, so it is not fresh prefill work. |
| `total_throughput_tps` | Input plus output tokens divided by wall time |
| `itl_ms_*` | Token arrival intervals, **only** when every event carries one explicit token ID and totals match server usage |
| `chunk_interval_ms_*` | Intervals between streamed chunks, which may contain several tokens |
| `client_queue_ms` | Time waiting for a concurrency slot in the load generator. Separate from TTFT. |

Distributions include the mean, p50, p90, p95, p99 and max. Client timings include network, proxy and parser buffering, so they do not isolate engine prefill, transfer or scheduler time.

**How to read aggregated against disaggregated:** disaggregation usually shows its benefit in **tail ITL/TPOT under concurrency with long prompts**. TTFT can rise slightly because of the transfer. Throughput depends on whether one prefill to one decode suits your input:output ratio.

---

## 7. Outputs and the comparison notebook

Each run creates `tracks/nvidia-dynamo/studies/<UTC timestamp>-<id>/`:

- `requests.csv`: one row per request, including errors
- `requests.jsonl`: every streamed event with its arrival time, for auditing. It can contain generated text.
- `summary.csv` and `summary.json`: the run's distributions and configuration identifiers
- `metadata.json`: exact arguments, dataset hash and the full `deployment.json`
- `metrics-before-*.prom` / `metrics-after-*.prom`: worker metric snapshots

```bash
python -m benchmarks.collect          # rebuilds tracks/nvidia-dynamo/studies/summary.csv from all runs
jupyter lab benchmarks/compare.ipynb   # or open it in your IDE
```

The notebook shows failure and validity counts first. It then groups repeated identical configurations and compares model × technology × backend with charts, which it can export as PNG or CSV. It never pools different datasets or deployments.

---

## 8. Rules for a fair comparison

- Use the same dataset file, output budget, sampling settings, reasoning mode, GPU count and client placement across the tracks being compared.
- Use at least three repetitions and more than eight sessions before quoting p99 figures.
- `--cache-state` is a label, not a flush. For cold-cache runs, restart the workers before each repetition.
- Before claiming a disaggregation result, show evidence that KV moved over RDMA (step 7 of the deploy guides). Size pools from the measured numbers with [blueprint 09](../blueprint/09-parallelism-and-sizing.md).
- Save GPU and driver inventory and resolved image digests with the results. Engine comparisons are **stack** comparisons.

**Status:** the benchmark code is unit-tested (metrics, streaming, failures, notebook). The H200 site includes live functional validation and a [matched 256K topology comparison](../tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/REPORT.md), with [raw results and executed analysis](../tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/). The comparison has one measured run per topology; it does not establish maximum capacity or repeatability. See the [performance runbook](../tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/PERFORMANCE.md) for larger sweeps.

---

**See also:** [blueprint 09 · Parallelism and sizing](../blueprint/09-parallelism-and-sizing.md) · [blueprint 10 · Production operations](../blueprint/10-production-operations.md)
