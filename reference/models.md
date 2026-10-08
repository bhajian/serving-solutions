# Model catalog and switching models

[Home](../README.md) › [Reference](README.md) › Models

The reference deployments in the B300 reference tracks 01–03 (tracks/nvidia-dynamo/sites/hgx-b300-2x8) serve **NVIDIA Nemotron 3 Ultra 550B-A55B NVFP4**. This page lists the other model profiles the repository knows about, and how to switch a deployment to one of them.

## Switching a reference deployment to another model

The hand-written deployment files spell out every flag, so switching models means editing a few clearly marked places. Change **every** worker file of the track (Node A and Node B, or all `3*.yaml`) and the frontend together.

| What | Where | Nemotron value | Example: Qwen3-Coder-480B FP8 |
|---|---|---|---|
| Weights path | `MODEL_DIR` in `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env`, or the `hostPath` volumes in Kubernetes | `/data/nemotron-ultra/model` | `/data/models/qwen-480b` |
| Revision check | `grep -qx <sha>` line in each worker command | `252a02f9…` | `003f183a92fbe5b9a8325aaa8b2ae797c91dd90f` |
| API model name | `--served-model-name` | `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4` | `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8` |
| Model-specific engine flags | vLLM: `--attention-backend` through `--reasoning-parser`. SGLang: none beyond `--trust-remote-code`. | Nemotron hybrid kernels + parsers | **Remove** them. Qwen needs none. |
| Model-specific env | `VLLM_ALLREDUCE_USE_SYMM_MEM` … `DYN_VLLM_APPEND_PREFILL_OUTPUT_TOKENS`, `SGLANG_DISABLE_DEEP_GEMM` | set | **Remove** |
| KV page size | vLLM `--block-size`, SGLang `--page-size`, **and** the frontend `--kv-cache-block-size` | 64 | vLLM 128, SGLang 64 |
| KV cache dtype | `--kv-cache-dtype` | vLLM `fp8`, SGLang `auto` | `auto` |
| Tool / reasoning parsers | `--dyn-tool-call-parser`, `--dyn-reasoning-parser` | `qwen3_coder`, `nemotron3` | `qwen3_coder`, no reasoning parser |
| Request defaults | `deployment.json` → `model.request_body` | disable thinking | `{}` |
| Run record | `deployment.json` → `model.model_id`, `revision`, `model_path` | Nemotron | Qwen |

The exact values for every profile are in [configs/models.yaml](../configs/models.yaml): `engine_args`, `dynamo_args`, `env`, `block_size`, `kv_cache_dtype`, and the `sglang:` sub-section. To see a complete, ready-made variant for comparison, generate it and diff it against the hand-written file:

```bash
python tools/render.py --target compose --model qwen-480b --out build/compose-qwen
diff <(grep -- '--' tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml) <(grep -- '- --' build/compose-qwen/node-a.yaml)
```

Download the new model on **both** nodes first (`python tools/download_model.py --model qwen-480b`), and stop both workers before switching.

## Profiles


[configs/models.yaml](../configs/models.yaml) keeps model ID, pinned revision, local weight directory, context ceiling, engine flags, request defaults and framework-specific arguments together. Profiles do not reuse Nemotron's Mamba/kernel flags for ordinary transformers.

| Profile | Checkpoint | Context ceiling used here | Notes |
|---|---|---:|---|
| `nemotron-ultra` | NVIDIA Nemotron 3 Ultra 550B NVFP4 | 1,048,576 | Preserves the manual guide's exact image/revision and model-specific flags |
| `qwen-480b` | Qwen3-Coder-480B-A35B-Instruct-FP8 | 262,144 | Large Qwen default; no implicit YaRN extension |
| `qwen-235b` | Qwen3-235B-A22B-Instruct-2507 | 262,144 | Alternative large Qwen |
| `deepseek-v4-flash` | DeepSeek-V4-Flash | 1,048,576 | Experimental TP8/TP8 adaptation; custom tokenizer mode |
| `deepseek-v4-pro` | DeepSeek-V4-Pro-0813 | 1,048,576 | Larger V4; disk capacity is tight on the recorded hosts |
| `kimi-k3` | Kimi-K3 | 1,048,576 | Upstream vLLM >=0.29, or NVIDIA's patched K3 preview; substantial additional disk space |

All start at **32,768** tokens, TP8, 0.80 GPU memory utilization, 8192 batched tokens and 32 sequences. Context ceilings are model configuration limits, not a promise that a chosen concurrency fits GPU memory. The local B300 TP8/TP8 configurations have not been inference-tested. Source links are in [sources.md](sources.md).

## Downloading and pinning a checkpoint on both nodes

Run on each GPU node. The downloader queries file sizes, checks remaining disk capacity including reserve, and downloads directly into the serving directory. It resolves the supplied revision to a SHA and writes `DEPLOYED_REVISION` and `DEPLOYMENT_MODEL.json` after successful download.

```bash
# Optional for repositories requiring authentication; no token is written to YAML.
read -rsp 'Hugging Face token: ' HF_TOKEN; echo
export HF_TOKEN

python tools/download_model.py --model qwen-480b --check-only
python tools/download_model.py --model qwen-480b
cat /data/models/qwen-480b/DEPLOYED_REVISION
```

The catalog already pins public checkpoint revisions. If testing another revision, pass `--revision SHA` to the downloader on **both nodes** and renderer. Use a new `--path`/`--model-path` when changing an existing directory's revision. The script refuses to mix tracked revisions. Verify that both nodes report the same SHA before starting workers.

Existing Nemotron weights from the manual guide can be reused. Each P/D node needs the whole checkpoint on disk; neither node loads just half the model's layers.

**Kimi storage:** the original guide reports 973 GiB free per node. The K3 recipe describes a checkpoint on the order of 1.5–1.7 TB, so provision a larger volume on **each** node or a suitably fast shared model volume before download. Query current repository sizes with `--check-only`. Also budget for container images, caches and retained models; several large checkpoints will not fit together on the original disks. Do not assume active MoE parameter count determines weight storage.

## Generating a variant with the optional render tool

```bash
python tools/render.py --target llmd --model deepseek-v4-flash \
  --max-model-len 262144 --max-num-seqs 4 --out build/llmd-deepseek
python tools/render.py --target compose --model qwen-480b \
  --max-model-len 262144 --max-num-seqs 4 --out build/compose-qwen
```

Stop both old workers before launching the new pair. Regenerate frontend settings as well as workers. The render output's `deployment.json` belongs with each benchmark run. Workers verify `DEPLOYED_REVISION` and the profile's minimum selected engine version before launch. Image overrides use `--image REPOSITORY:TAG@sha256:DIGEST`; both workers receive the same image. For complete reproducibility, replace tag-only engine/sidecar images with pulled registry digests and retain node/driver/runtime inventories. Model-specific images in `configs/models.yaml` take precedence over cluster defaults; an explicit `--image` takes precedence over both.

## Compatibility limits

The details below describe the original vLLM profiles. Each model also has an independent `sglang` section; use `--backend sglang` and follow the [SGLang compatibility notes](vllm-vs-sglang.md). vLLM parser/kernel flags are never copied into SGLang.

- **Kimi on Dynamo:** automatically uses `nvcr.io/nvidia/ai-dynamo/vllm-runtime:1.5.0-kimi-k3-dev.1`, an official experimental image carrying K3 patches on a vLLM 0.28.0 base. This is an explicit exception to upstream's version floor, scoped to that model-specific image. The frontend uses Dynamo's native chat processor and the workers select K3 tool/reasoning parsers. NVIDIA's reference targets GB300/NVLink; this project's B300/InfiniBand TP8 adaptation remains unvalidated. It serves text only, with speculative decoding disabled and no draft-model download. Do not substitute the Nemotron 1.4.0 image or upgrade vLLM in place. [NVIDIA preview release](https://github.com/ai-dynamo/dynamo/releases/tag/v1.5.0-kimi-k3-dev.1).
- **Kimi on llm-d:** the pinned vLLM 0.30.0 meets the recipe's version floor. That alone does not qualify this symmetric TP8 P/D adaptation, GPU memory headroom, hybrid-state transfer or tool output. Begin at low concurrency; adjust GPU memory utilization only after inspecting available KV capacity. K3 always thinks, so its latency is not directly comparable with a non-thinking model without recording that difference.
- **DeepSeek V4:** vLLM uses `--tokenizer-mode deepseek_v4` because the checkpoint does not supply a standard Jinja chat template. For local benchmark token counting, pass `--deepseek-v4-encoder /path/to/checkpoint/encoding/encoding_dsv4.py --trust-remote-code` to the dataset generator, using the encoder from the same pinned revision as the server. Alternatively use the vLLM worker's `/tokenize` endpoint. The [Nebius H200 SGLang deployment](../tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/) includes a complete example. Defaults here request non-thinking behavior; for reasoning tests use the model's documented `chat_template_kwargs` and a separate comparison cohort. Think Max needs at least a 384K context budget.
- **Dynamo parser integration:** DeepSeek/Kimi profiles select the native tool/reasoning parser names from NVIDIA's recipes. The bundled benchmark replays recorded tool histories and measures generated payloads; it does not validate autonomous tool execution or output schemas. Confirm native tool output with the selected image before using these profiles for a live agent.
- **llm-d Nemotron:** the model-specific flags are carried into the newer stock vLLM image as a candidate. Check its CLI, NVFP4/Mamba/NIXL support and parser plugin import before assuming equivalence with NVIDIA's patched image. For closer engine parity, `--image` may select the original NVIDIA runtime while still launching `vllm serve`; that combination also needs validation.

Adding another model means adding a full profile with its actual model ID, immutable revision, context limit, compatible image, engine/parser flags and request defaults. Changing only `--served-model-name` does not change the weights.
