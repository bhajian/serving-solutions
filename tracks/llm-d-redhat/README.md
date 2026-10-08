# Track 2 · llm-d + Red Hat AI

[Home](../../README.md) › [Tracks](../README.md) › llm-d + Red Hat AI

**Executive summary.** Kubernetes-native serving with the llm-d router (endpoint picker and
Envoy on the Gateway API Inference Extension) in front of vLLM from the **Red Hat AI Inference
Server** (RHAIIS) image. llm-d publishes its best practices as *well-lit paths*; this track
gives each of the eight core paths a folder with a guide, deployable manifests for a model on
a site, and a test. Path 01 is deployed on 4 × 8 H200 with DeepSeek V4 Pro, and its
[256K routing study](studies/deepseek-v4-pro-256k-routing/README.md) is running.

| Folder | Contents |
| --- | --- |
| [install/](install/README.md) | What every path needs once per cluster: InferencePool CRDs, the router chart, the RHAIIS image and its pull secret |
| [paths/](paths/README.md) | The eight well-lit paths, each with a guide and per-site instances |
| [studies/](studies/README.md) | Tests run against the paths: protocol, drivers, data, report |

## The eight well-lit paths

Upstream guides: llm-d [release-0.10](https://github.com/llm-d/llm-d/tree/release-0.10/guides) (llm-d v0.10.0, router v0.11.0).

| # | Path | Adds | Framework pattern (D1) | Status here |
| --- | --- | --- | --- | --- |
| 01 | [Optimized baseline](paths/01-optimized-baseline/README.md) | Prefix-cache-aware and load-aware routing in the llm-d router | Aggregated + prefix-aware routing | **Deployed**: DeepSeek V4 Pro, 4 × TP8 H200; study running |
| 02 | [Precise prefix-cache routing](paths/02-precise-prefix-cache-routing/README.md) | Global index of the real vLLM KV cache from KV events | Prefix routing on exact KV state | Planned |
| 03 | [Predicted-latency routing](paths/03-predicted-latency-routing/README.md) | Routing on live-trained TTFT/TPOT predictions | Latency-predictive routing | Planned |
| 04 | [Tiered prefix cache](paths/04-tiered-prefix-cache/README.md) | KV offload to CPU memory and disk | KV tiering | Planned |
| 05 | [P/D disaggregation](paths/05-pd-disaggregation/README.md) | Prefill and decode pools, NIXL transfer, routing sidecar | P/D disaggregation | Reference manifests (B300, Qwen3-Coder 480B) |
| 06 | [Wide expert parallelism](paths/06-wide-ep/README.md) | Multi-node DP/EP for large MoE | Wide EP + DP attention | Planned |
| 07 | [Flow control](paths/07-flow-control/README.md) | Queuing, priority and fairness in the router | Admission control | Planned |
| 08 | [Workload autoscaling](paths/08-workload-autoscaling/README.md) | Scaling on queue depth, in-flight work and KV pressure | SLO-driven autoscaling | Planned |

Workload guides upstream (agentic, batch, multimodal serving) compose these eight; the
framework's workload matrix ([2 · Decide](../../framework/2-decide/README.md#d1--serving-pattern))
plays the same role here.

## Support and platforms

Checked 2026-10-08; confirm against Red Hat's current documentation before committing.

| Deployment | Red Hat support position |
| --- | --- |
| Red Hat OpenShift AI with Distributed Inference with llm-d | Red Hat product (models as KServe `LLMInferenceService`) |
| AKS, CoreWeave CKS, EKS via the `rhai-on-xks` chart | Technology Preview ([docs](https://docs.redhat.com/en/documentation/red_hat_ai_inference/3.5/html/deploy_distributed_inference_with_llm-d_on_aws_azure_or_coreweave_kubernetes_service)) |
| RHAIIS container on other Kubernetes | Third-party support policy for the container |
| **This track on Nebius managed Kubernetes** | Upstream llm-d router + RHAIIS image: the image is Red Hat's, the router is community |

Red Hat validates specific checkpoints. For DeepSeek V4 Pro it lists the preview weights
(`RedHatAI/DeepSeek-V4-Pro`), not the 0813 release served in path 01.
