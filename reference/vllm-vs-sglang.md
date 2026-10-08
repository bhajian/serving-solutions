# vLLM and SGLang side by side

[Home](../README.md) › [Reference](README.md) › vLLM vs SGLang

Dynamo wraps both engines with the same frontend, router and discovery, so deployment tracks 02 and 03 differ only in the workers. This page maps the settings between them.

## Runtime and launch

| | vLLM | SGLang |
|---|---|---|
| Dynamo worker | `python3 -m dynamo.vllm` | `python3 -m dynamo.sglang` |
| Dynamo image | `nvcr.io/nvidia/ai-dynamo/vllm-runtime:1.4.0` (vLLM 0.26.0), pinned by digest | `nvcr.io/nvidia/ai-dynamo/sglang-runtime:1.4.0` (SGLang 0.5.16 base) |
| llm-d worker ([llm-d path 05, B300](../tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/)) | `vllm serve`, image `vllm/vllm-openai:v0.30.0` | `python3 -m sglang.launch_server`, image `lmsysorg/sglang:v0.5.20` |
| Model path flag | `--model /model` | `--model-path /model` |

Each engine uses a complete engine-specific image. Never pip-install one engine into the other's image.

## Capacity flags (same meaning, different names)

| Concept | vLLM | SGLang | Reference value |
|---|---|---|---|
| Context window | `--max-model-len` | `--context-length` | 32768 |
| Concurrent sequences | `--max-num-seqs` | `--max-running-requests` | 32 |
| Per-step prefill budget (chunked prefill) | `--max-num-batched-tokens` | `--chunked-prefill-size` | 8192 |
| GPU memory share | `--gpu-memory-utilization` | `--mem-fraction-static` | 0.80 |
| KV page size | `--block-size` | `--page-size` | 64 |
| KV cache dtype | `--kv-cache-dtype fp8` | `--kv-cache-dtype auto` | differs: record it when comparing |
| Prefix caching | `--enable-prefix-caching` | radix cache, on by default | on |

The two schedulers interpret these limits differently. Equal numbers do not guarantee equal memory allocation or batching behavior.

## Disaggregation and KV transfer

| | vLLM (track 02) | SGLang (track 03) |
|---|---|---|
| Role | `--disaggregation-mode prefill\|decode` | `--disaggregation-mode prefill\|decode` |
| Transfer | `--kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_both"}'` | `--disaggregation-transfer-backend nixl` |
| Handshake | NIXL side channel: `VLLM_NIXL_SIDE_CHANNEL_HOST`, port 5600 | Bootstrap server on prefill: `--disaggregation-bootstrap-port 8998` |
| UCX selection | `UCX_NET_DEVICES`, `UCX_TLS`, `UCX_RNDV_*` | `SGLANG_DISAGGREGATION_NIXL_BACKEND=UCX`, `SGLANG_DISAGGREGATION_NIXL_BACKEND_PARAMS={"ucx_devices": ...}`, plus `UCX_*` |
| Transfer direction | Decode pulls with RDMA reads | Prefill sends after the bootstrap handshake |
| llm-d sidecar connector | `nixlv2` | `sglang` (with `SGLANG_BOOTSTRAP_PORT=8998`) |
| llm-d vLLM roles | `kv_producer` / `kv_consumer`, `kv_load_failure_policy=fail` | n/a |

## Ports

| Port | vLLM | SGLang |
|---|---|---|
| Public API | Dynamo frontend 8000 | Dynamo frontend 8000 |
| Worker health and metrics | 8081 (`DYN_SYSTEM_PORT`) | 8081 |
| Engine internal HTTP | none under Dynamo | 30000 |
| KV events (ZMQ) | `tcp://127.0.0.1:5571` | `tcp://*:5571` |

## Parsers and request behavior

- Parsers are engine-specific and never copied between engines. Under Dynamo, the `--dyn-tool-call-parser` / `--dyn-reasoning-parser` flags are used. Nemotron on vLLM additionally loads the model's own reasoning-parser plugin.
- Benchmarks: `--token-ids`, which gives exact per-token ITL, uses a vLLM extension and is rejected for SGLang. The dataset generator's remote `/tokenize` mode follows vLLM's contract. For SGLang, use local tokenizer files.
- Results always carry the `backend` column. The notebook never pools vLLM and SGLang runs.

## Qualification status

- vLLM + Nemotron: the flags come from NVIDIA's recipe, and the worker configuration initialized on the reference hosts.
- SGLang + Nemotron: aggregated serving follows NVIDIA's published cookbook. Disaggregated NIXL transfer of the hybrid model's state is **not** qualified. If it fails, use a standard transformer such as Qwen3-Coder-480B for SGLang comparisons ([models.md](models.md#switching-a-reference-deployment-to-another-model)).
- NIXL errors, cancellations and timeouts need particular attention with SGLang P/D. See [sources.md](sources.md) for the pinned upstream references.
