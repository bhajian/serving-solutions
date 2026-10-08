# Glossary

[Home](../README.md) › [Reference](README.md) › Glossary

Terms are defined once here and used with these meanings throughout the repository.
Measurement definitions match [benchmarks/README.md](../benchmarks/README.md).

## Latency and throughput

| Term | Definition |
| --- | --- |
| **TTFT** (time to first token) | Request start to the first generated payload at the client. Includes gateway, routing, queueing, prefill and, in disaggregated mode, the KV handoff. |
| **ITL** (inter-token latency) | The gap between two consecutive streamed tokens at the client. Reported as a distribution pooled over every token of every valid request (p50, p99, p99.9, max). The server-side SGLang histogram is reported alongside. |
| **TPOT** (time per output token) | Per request: (last token time − first token time) / (output tokens − 1). The mean of that request's ITLs. AIPerf and genai-perf call this `inter_token_latency`. |
| **E2E latency** | Request start to stream completion. |
| **Output tokens/s** | Valid output tokens of the run divided by its wall time. |
| **Goodput** | Requests per second that individually meet **both** targets: TTFT ≤ the TTFT SLO, and the p99 of their own ITLs ≤ the ITL SLO. The primary comparison metric for realistic traffic. |
| **SLO attainment** | The share of valid requests that meet both targets. |
| **Valid measurement** | A request that succeeded with server-reported usage, the exact forced output length where one was forced, and a prompt within the context window. Invalid requests are counted, never silently dropped. |

## Workload

| Term | Definition |
| --- | --- |
| **ISL / OSL** | Input and output sequence length, in tokens. |
| **Closed loop** | A fixed number of requests in flight; a new one starts when one finishes. |
| **Open loop** | Requests arrive on a schedule (Poisson or constant rate) whether or not earlier ones have finished. |
| **Prefix reuse** | A later request whose prompt starts with tokens already in the KV cache, so that part of prefill is skipped. |

## Serving architecture

| Term | Definition |
| --- | --- |
| **Prefill** | Processing the prompt to build its KV cache. Compute-bound. |
| **Decode** | Generating output tokens one step at a time. Memory-bandwidth-bound. |
| **Aggregated** | Every worker runs prefill and decode for its own requests. |
| **Disaggregated (PD)** | Separate prefill and decode workers; the KV cache (and Mamba state for hybrid models) moves from prefill to decode. |
| **P:D ratio** | Prefill workers (or GPUs) to decode workers (or GPUs) in a disaggregated graph. |
| **KV cache** | Per-token attention keys and values kept for the rest of a request. |
| **TP / EP / DP attention** | Tensor parallelism (each layer split across GPUs); expert parallelism (MoE experts spread across GPUs); data-parallel attention (each rank holds whole sequences' attention state, avoiding KV duplication for MLA). |
| **MLA** | Multi-head latent attention (DeepSeek), which stores a compressed latent KV per token. |
| **MTP** | Multi-token prediction: a draft head proposes tokens that the model verifies, a form of speculative decoding. |
| **Speculative decoding** | A drafter proposes *k* tokens; the target model verifies them in one pass and keeps the longest accepted prefix. Lossless under standard rejection sampling ([chapter 13](../blueprint/13-speculative-decoding.md)). |
| **Acceptance length** | Mean tokens committed per verify step, including the bonus token. SGLang reports it as `sglang:spec_accept_length`. |
| **EAGLE / NextN / DSpark** | Drafters: EAGLE uses the target's hidden states; NextN is DeepSeek's checkpoint-native MTP head; DSpark drafts a whole block in one parallel pass (Kimi K3). |
| **KDA** | Kimi Delta Attention: a linear-attention layer with a fixed-size recurrent state per sequence, used for 69 of Kimi K3's 93 layers. |
| **DCP** | Decode context parallelism: shards a sequence's KV by position across decode ranks instead of replicating latent KV on every TP rank. |
| ***R*** (prefill-to-decode work ratio) | The P:D ratio a workload needs: ISL × (1 − reuse) / OSL × *Sd* / (*Tp* × TPOT) ([chapter 15](../blueprint/15-workload-driven-design.md)). |
| **Transfer intensity** | KV bytes moved by P/D per unit of prefill compute saved. Low for MLA, hybrid and large MoE models; high for small dense models. |

## Dynamo and Kubernetes

| Term | Definition |
| --- | --- |
| **DynamoGraphDeployment (DGD)** | The Dynamo operator's custom resource describing one serving graph: frontend, workers, Planner. |
| **DynamoGraphDeploymentRequest (DGDR)** | An SLA-driven request: the operator profiles the model and proposes or creates a DGD. |
| **Frontend / KV router** | Dynamo's OpenAI-compatible HTTP entry point. Routes each request to a worker by expected KV overlap and load. |
| **Planner** | Dynamo component that adjusts prefill and decode replicas from Prometheus metrics against TTFT/ITL targets (mean values in 1.4.0). |
| **NIXL / UCX** | NVIDIA Inference Xfer Library, the KV transfer layer, running over UCX (RDMA, NVLink, CUDA IPC). |
| **GPUDirect RDMA** | NIC reads and writes GPU memory directly, without a host copy. |
| **Grove / KAI** | Grove reconciles a graph into gang-scheduled PodCliqueSets; the KAI scheduler places them as a unit. |
| **Lab / production path** | Lab: the hand-written manifests that produced `tracks/nvidia-dynamo/studies/`. Production: the operator-managed graphs and overlays in `tracks/nvidia-dynamo/graphs` and `tracks/nvidia-dynamo/production`. |
| **UNVALIDATED** | Prepared and checked offline, but not yet run on hardware with results committed. |
