# 04 · Disaggregated serving with llm-d

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [llm-d + Red Hat AI](../../../README.md) › [Paths](../../README.md) › [05 · P/D disaggregation](../README.md) › 04 · llm-d

[llm-d](https://github.com/llm-d/llm-d) is the Kubernetes-native option for the serving control plane. It uses the same engines and the same NIXL KV transfer as Dynamo, but routes through the Kubernetes Gateway API Inference Extension and coordinates prefill/decode in a sidecar next to the decode engine. Use this track to deploy llm-d, or to compare the **control-plane layer** on identical hardware. The blueprint compares the two in [04 · Orchestration layer](../../../../../blueprint/04-orchestration-layer.md).

![Dynamo vs llm-d: in Dynamo the frontend and KV router coordinate prefill and decode; in llm-d an Envoy gateway asks the endpoint picker for a pod and a sidecar on the decode pod coordinates prefill](../../../../../assets/diagrams/png/production-topology.png)

| | Dynamo (02/03) | llm-d (this track) |
|---|---|---|
| Entry point | Dynamo frontend (Python, OpenAI API) | Envoy proxy + endpoint picker, installed by Helm chart |
| Discovery | etcd | Kubernetes labels + `InferencePool` CRD |
| P/D coordination | Dynamo frontend and worker wrappers | Routing sidecar next to the decode engine |
| Engines | `dynamo.vllm` / `dynamo.sglang` | Stock `vllm serve` / `sglang.launch_server` |
| Platform | Docker or Kubernetes | Kubernetes only (1.33+ for native sidecars) |

## Deploy

| Engine | Deploy guide |
|---|---|
| vLLM 0.30.0 | [vllm/README.md](vllm/README.md) |
| SGLang 0.5.20 | [sglang/README.md](sglang/README.md) |

**Different model from the Dynamo tracks.** These manifests serve `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8` from `/data/models/qwen-480b`. To compare fairly with Dynamo, deploy the Dynamo track with the same model ([reference/models.md](../../../../../reference/models.md#switching-a-reference-deployment-to-another-model)), or regenerate these files for Nemotron with `tools/render.py --target llmd` ([tools/](../../../../../tools/)).

**Generated files.** Unlike tracks 01 to 03, these manifests were produced by [tools/render.py](../../../../../tools/render.py). They are plain YAML and readable, but not hand-annotated. The pinned versions are llm-d guide v0.10.0 and router/sidecar v0.11.0. See [reference/sources.md](../../../../../reference/sources.md). Hand-annotated llm-d manifests for Nemotron are on the [roadmap](../../../../../ROADMAP.md).

---

**Next:** [benchmarks](../../../../../benchmarks/README.md) · [blueprint 10 · Production operations](../../../../../blueprint/10-production-operations.md)
