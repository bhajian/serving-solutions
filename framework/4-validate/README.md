# 4 · Deploy and validate

[Home](../../README.md) › [Framework](../README.md) › 4 · Deploy and validate

**Output:** a study, meaning a protocol, its data and a report, filed under the track that
ran it. **Gate:** the acceptance criteria from the design record are met, and the evidence
can be re-checked by someone else.

## Deploy

Follow the implementation chosen in D4: a Dynamo graph or overlay
([track 1](../../tracks/nvidia-dynamo/README.md)) or an llm-d well-lit path
([track 2](../../tracks/llm-d-redhat/README.md)). Cluster prerequisites shared by both are in
[platform/](../../platform/README.md).

## Validation ladder

| Level | Question | How | Typical duration |
| --- | --- | --- | --- |
| L0 · Functional | Does the API work end to end? | Smoke tests: models list, streaming and non-streaming chat, tool calling, a long-context retrieval check | Minutes |
| L1 · Calibration | What are the real per-worker numbers? | Engine KV capacity from logs; cold prefill tokens/s at the target ISL; decode tokens/s at the planned batch | < 1 h |
| L2 · Acceptance | Does the design meet the SLO for the profile's goal? | The study type for the goal (below) at the profile's load | 1–3 h |
| L3 · Comparison | Is it better than the alternative? | The same study on two patterns, two paths or two tracks, same dataset and hardware | 2–6 h |

| Goal | Study type | Instrument | Template study |
| --- | --- | --- | --- |
| Long context | Multi-turn sessions over a long shared context; TTFT by turn, cached tokens per request | `benchmarks.run` | [Dynamo 256K](../../tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/README.md), [llm-d 256K routing](../../tracks/llm-d-redhat/studies/deepseek-v4-pro-256k-routing/README.md) |
| Output-optimized | Forced long outputs at high concurrency; ITL distribution and stalls | `benchmarks.long_decode` | [8K in / 128K out](../../tracks/nvidia-dynamo/studies/nemotron-3-nano-8k-128k-comparison/README.md) |
| SLA | Open-loop arrivals, goodput at p99 TTFT and ITL, swept over load | `benchmarks.loadgen`, `benchmarks.sweep` | [Planned 01](../../tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/README.md) |
| Throughput and cost | Closed loop at maximum batch, cost per million tokens | `benchmarks.loadgen --gpu-hour-usd` | — |

## Rules every study follows

From [benchmarks/README.md](../../benchmarks/README.md#8-rules-for-a-fair-comparison):

- One dataset file per comparison, recorded by SHA256, and identical request bodies across arms.
- Images pinned by digest and model revision verified at startup.
- KV and prefix caches reset before each arm, with the acknowledgements recorded.
- Load generated inside the cluster, through the same entry point for every arm.
- Warmups and pilots recorded separately and excluded from results.
- Raw evidence archived with a checksum manifest; summaries kept in the repository.

## Study lifecycle and layout

`planned → running → complete`. Each track keeps its studies in `tracks/<track>/studies/<name>/`:
a README (question, protocol, verdict), the driver scripts, the data that notebooks read, and
the analysis notebook. Raw evidence moves to release archives
([tools/archive_results.py](../../tools/archive_results.py)). Dynamo's prepared but unrun
experiments are generated into [studies/planned/](../../tracks/nvidia-dynamo/studies/planned/README.md).

## Evidence register

| Study | Track | Question | Status | Verdict |
| --- | --- | --- | --- | --- |
| [deepseek-v4-pro-256k-comparison](../../tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/README.md) | Dynamo + SGLang | 256K multi-turn: 2 aggregated TP8 vs 1P + 1D on 2 × H200 | complete | Aggregated 5.53× faster; follow-ups hit the prefix cache |
| [nemotron-3-nano-128k-comparison](../../tracks/nvidia-dynamo/studies/nemotron-3-nano-128k-comparison/README.md) | Dynamo + SGLang | 128K in / 256 out | complete | Aggregated 1.62× faster |
| [nemotron-3-nano-8k-128k-comparison](../../tracks/nvidia-dynamo/studies/nemotron-3-nano-8k-128k-comparison/README.md) | Dynamo + SGLang | 8K in / 128K out at the KV limit | complete | Aggregated 1.34× throughput; P/D removed prefill stalls (worst ITL 1.1 s vs 40.4 s) |
| [deepseek-v4-pro-256k-routing](../../tracks/llm-d-redhat/studies/deepseek-v4-pro-256k-routing/README.md) | llm-d + RHAIIS vLLM | 256K multi-turn on 4 × TP8: cache-unaware vs prefix-aware scheduling | running | — |
| [Planned 00–09](../../tracks/nvidia-dynamo/studies/planned/README.md) | Dynamo | P:D sweep, KV router, Planner, reliability, DeepSeek layout, scheduling, chunk size, soak, B300 | planned | — |

---

**Next:** [5 · Operate](../5-operate/README.md)
