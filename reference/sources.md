# Version and source notes

[Home](../README.md) › [Reference](README.md) › Sources

Reviewed 2026-09-29. The original Docker guide ([manual-docker-walkthrough.md](../tracks/nvidia-dynamo/sites/hgx-b300-2x8/manual-docker-walkthrough.md)) supplies the Nemotron model revision, image digest, node IPs and hardware inventory. The local files are adaptations, not vendor qualification of B300 TP8/TP8.

| Component | Pin / provenance |
|---|---|
| Dynamo | 1.4.0; image digest retained from the original guide |
| Bundled vLLM in Dynamo | 0.26.0 in NVIDIA's release matrix |
| Kimi-specific Dynamo runtime | `1.5.0-kimi-k3-dev.1`, patched vLLM 0.28.0 base; experimental |
| llm-d guide | v0.10.0, commit `f22bbaf3173a326d214f06d7c769b905cb3f489a` |
| llm-d router chart and sidecar | v0.11.0 |
| Standalone router OCI chart digest observed | `sha256:56a5635f5fd6e1252f802e06186cf9c4c60bcb95b7911b0867660a7db4d04c1c` |
| llm-d vLLM image | `vllm/vllm-openai:v0.30.0` from the pinned release's image component |
| InferencePool CRD | Gateway API Inference Extension v1.5.0, matching llm-d's pinned guide environment |
| Checkpoints | Immutable Hugging Face SHAs in `configs/models.yaml` |

Primary references:

- [NVIDIA Nemotron Ultra recipe](https://docs.nvidia.com/dynamo/dev/recipes/nemotron-3-ultra) and [reference disaggregated manifest](https://github.com/ai-dynamo/dynamo/blob/main/recipes/nemotron-3-ultra/vllm/disagg-b200-agentic-256K/deploy.yaml).
- [Dynamo release compatibility](https://docs.nvidia.com/dynamo/v1.4.0/reference/compatibility) and [health endpoints](https://docs.nvidia.com/dynamo/v1.4.0/reference/observability/health-checks).
- [Pinned llm-d P/D guide](https://github.com/llm-d/llm-d/blob/f22bbaf3173a326d214f06d7c769b905cb3f489a/guides/pd-disaggregation/README.md), [release environment](https://github.com/llm-d/llm-d/blob/f22bbaf3173a326d214f06d7c769b905cb3f489a/guides/env.sh), [vLLM image pin](https://github.com/llm-d/llm-d/blob/f22bbaf3173a326d214f06d7c769b905cb3f489a/guides/recipes/modelserver/components/images/gpu-vllm/release/kustomization.yaml), and [sidecar options](https://github.com/llm-d/llm-d-router/blob/v0.11.0/pkg/sidecar/proxy/options.go).
- [NIXL usage](https://docs.vllm.ai/en/latest/features/nixl_connector_usage/) and [compatibility matrix](https://docs.vllm.ai/en/latest/features/nixl_connector_compatibility/).
- [Qwen 480B FP8](https://huggingface.co/Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8) and [Qwen 235B](https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507).
- [DeepSeek V4 Flash model card](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash), [V4 Pro vLLM recipe](https://recipes.vllm.ai/deepseek-ai/DeepSeek-V4-Pro), and [V4 Flash recipe](https://recipes.vllm.ai/deepseek-ai/DeepSeek-V4-Flash).
- [Kimi K3 model card](https://huggingface.co/moonshotai/Kimi-K3) and [vLLM recipe](https://recipes.vllm.ai/moonshotai/Kimi-K3).
- [NVIDIA K3 preview release](https://github.com/ai-dynamo/dynamo/releases/tag/v1.5.0-kimi-k3-dev.1), [K3 Dynamo P/D recipe](https://github.com/ai-dynamo/dynamo/blob/6822babc5c542350127e490f4fb8f2042855559c/recipes/kimi-k3/vllm/disagg-gb300-agentic/deploy.yaml), and [DeepSeek V4 Dynamo parser settings](https://github.com/ai-dynamo/dynamo/blob/6822babc5c542350127e490f4fb8f2042855559c/recipes/deepseek-v4/deepseek-v4-flash/vllm/disagg-b200-agentic/deploy.yaml).
- Kimi K3 serving techniques (chapters 13–15, reviewed 2026-10-02): [vLLM day-0 K3 post](https://vllm.ai/blog/2026-07-27-k3), [LMSYS / SGLang day-0 K3 post](https://www.lmsys.org/blog/2026-07-27-kimi-k3-day0-support/), [RadixArk K3 DSpark draft](https://huggingface.co/RadixArk/Kimi-K3-DSpark), [Inferact K3 DSpark draft](https://huggingface.co/Inferact/Kimi-K3-DSpark), [SGLang PP prefill + DCP decode with DSpark](https://github.com/sgl-project/sglang/pull/40045), [vLLM DSpark KV-group fix](https://github.com/vllm-project/vllm/pull/56952), and the [Kimi Linear report](https://arxiv.org/abs/2510.26692). These figures are vendor- or community-reported on GB300 and are not reproduced here.
- [vLLM streaming token-ID contract](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/).

The llm-d manifests retain the published NIXL producer/consumer and routing-sidecar flow. They use one worker per role rather than the upstream reference replica/TP ratio. The router does not reuse upstream's model-specific measured peak-prefill throughput. The checked-in rendered router is generated from the upstream Apache-2.0 chart, whose source and license are in [llm-d/llm-d-router](https://github.com/llm-d/llm-d-router/tree/v0.11.0).


## SGLang backend references

- [Dynamo 1.4.0 SGLang P/D + KV router launch example](https://github.com/ai-dynamo/dynamo/blob/v1.4.0/examples/backends/sglang/launch/disagg_router.sh), [runtime image version](https://github.com/ai-dynamo/dynamo/blob/v1.4.0/container/context.yaml), and [native/engine parser mutual exclusion](https://github.com/ai-dynamo/dynamo/blob/v1.4.0/components/src/dynamo/sglang/args.py).
- [llm-d v0.10.0 SGLang prefill configuration](https://github.com/llm-d/llm-d/blob/v0.10.0/guides/pd-disaggregation/modelserver/gpu/sglang/base/patch-prefill.yaml), [decode configuration](https://github.com/llm-d/llm-d/blob/v0.10.0/guides/pd-disaggregation/modelserver/gpu/sglang/base/patch-decode.yaml), [SGLang sidecar](https://github.com/llm-d/llm-d/blob/v0.10.0/guides/recipes/modelserver/base/single-host/pd/sglang/patch-sidecar.yaml), and [0.5.20 image pin](https://github.com/llm-d/llm-d/blob/v0.10.0/guides/recipes/modelserver/components/images/gpu-sglang/release/kustomization.yaml).
- [SGLang 0.5.20 disaggregation fields](https://github.com/sgl-project/sglang/blob/v0.5.20/python/sglang/srt/arg_groups/fields/disagg.py), [NIXL transport](https://github.com/sgl-project/sglang/blob/v0.5.20/python/sglang/srt/disaggregation/nixl/conn.py), and [DeepSeek V4 page/attention defaults](https://github.com/sgl-project/sglang/blob/v0.5.20/python/sglang/srt/arg_groups/model_overrides/deepseek_v4.py).
- [NVIDIA Nemotron Ultra SGLang cookbook](https://github.com/NVIDIA-NeMo/Nemotron/blob/main/usage-cookbook/Nemotron-3-Ultra/sglang_cookbook.ipynb) (aggregated serving), and [Kimi K3 SGLang Dynamo recipe at the reviewed commit](https://github.com/ai-dynamo/dynamo/blob/6822babc5c542350127e490f4fb8f2042855559c/recipes/kimi-k3/sglang/disagg-gb300-agentic/deploy.yaml) (Mooncake/NVLink reference).

SGLang profiles deliberately use SGLang parser names and flags. Their symmetric TP8 NIXL settings are local adaptations, with no GPU inference or transfer validation performed here. Image floors are startup checks, not compatibility guarantees.
