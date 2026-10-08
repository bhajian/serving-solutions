# 01 · Aggregated serving · vLLM

[Home](../../../../../../README.md) › [Tracks](../../../../../README.md) › [NVIDIA Dynamo](../../../../README.md) › [Sites](../../../README.md) › [hgx-b300-2x8](../../README.md) › [01-aggregated](../README.md) › vLLM

Aggregated Dynamo deployment with **vLLM** workers. This is the reference engine: its Nemotron 3 Ultra flags come from NVIDIA's Dynamo recipe, and the same image and revision completed worker initialization on the reference hosts.

| Platform | Deploy guide | Files |
|---|---|---|
| Docker Compose | [docker/README.md](../../compose/01-aggregated/vllm/README.md) | `node-a.yaml`, `node-b.yaml` |
| Kubernetes | [kubernetes/README.md](KUBERNETES.md) | numbered manifests `00-` … `30-` |

| Setting | Value |
|---|---|
| Image | `nvcr.io/nvidia/ai-dynamo/vllm-runtime:1.4.0`, pinned by digest (bundles vLLM 0.26.0) |
| Model | `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4`, revision `252a02f…` |
| Workers | 1 or 2 replicas × 8 GPUs, TP8, 32K context |

Compare it against: [02 · Dynamo disaggregated · vLLM](../../02-dynamo-disagg-vllm/).
