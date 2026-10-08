# Nemotron 3 Nano on the Nebius H200 cluster

This site profile runs `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` with Dynamo
1.4.0 and SGLang 0.5.16 on two eight-GPU H200 nodes. The context window is
131,072 tokens. [BENCHMARK-128K.md](../../../studies/nemotron-3-nano-128k-comparison/REPORT.md) records the matched
128K-input comparison and its validation status.
[BENCHMARK-8K-128K.md](../../../studies/nemotron-3-nano-8k-128k-comparison/REPORT.md) reverses the workload: 8K input,
128K forced output, with four TP4 workers at 262,144 context (`40-workers-tp4*.yaml`,
rendered by `render_tp4.py`, with the round-robin `31-frontend-round-robin.yaml`).

This profile **replaces the workers and frontend in the existing `deepseek-v4-pro`
namespace**. It uses the same LoadBalancer and bound `model-0`/`model-1` PVCs as
[track 05](../deepseek-v4-pro/). Do not apply both profiles at once.
The Kubernetes namespace is retained for PVC access; Dynamo discovery uses the
separate logical namespace `nemotron-3-nano`.

## Model and persistent storage

The pinned checkpoint revision is `bf77c3174f68ad409e1c2aa60daeb46e32d1c606`.
The download Jobs store it under `.models/nemotron-3-nano-bf16` on each existing
1500Gi RWO Nebius SSD PVC. DeepSeek's original weights remain at the PVC root.
Workers mount the Nemotron directory read-only at `/model`; runtime/kernel caches
live in its `.runtime` subdirectory through separate writable mounts.

Pod restarts and topology changes reuse these weights and caches. These are two
persistent network block volumes, not a shared RWX filesystem. Deleting the PVCs
or namespace can delete both models' disks; neither is part of mode switching.
The completed download Jobs need not be rerun when changing serving topology.

## Deploy and change topology

The two existing PVCs and the `hf-token` Secret (key `HF_TOKEN`) must already be
present. Use `--context $KUBE_CONTEXT` for all operations; the default local context
is a different cluster. Node selectors are specific to this site.

```bash
SITE=tracks/nvidia-dynamo/sites/nebius-h200-2x8/nemotron-3-nano
kubectl --context $KUBE_CONTEXT apply -f "$SITE/lab/as-measured/model-download/10-model-download.yaml"
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro wait --for=condition=complete \
  job/nemotron-download-0 job/nemotron-download-1 --timeout=20m
kubectl --context $KUBE_CONTEXT apply -f "$SITE/lab/as-measured/etcd/20-etcd.yaml" -f "$SITE/lab/as-measured/frontend-kv-router/30-frontend.yaml"
# Disaggregated: one TP8 prefill worker and one TP8 decode worker.
kubectl --context $KUBE_CONTEXT apply -f "$SITE/lab/as-measured/workers-tp8-disaggregated/40-workers-disaggregated.yaml"
# Alternatively, aggregated: two TP8 replicas, one on each node.
# kubectl --context $KUBE_CONTEXT apply -f "$SITE/lab/as-measured/workers-tp8-aggregated/40-workers.yaml"
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro rollout status deployment/worker-0 --timeout=20m
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro rollout status deployment/worker-1 --timeout=20m
```

`kustomization.yaml` selects aggregated workers. To restore DeepSeek, apply track
05's `30-frontend.yaml` and `40-workers.yaml`, then wait for both workers to become
ready. Switching either way interrupts the endpoint while workers restart.

Both modes allocate 16 GPUs to match the previous experiment. This is a topology
comparison, not a recommendation that this 30B model needs TP8. Worker settings
are identical except for prefill/decode roles and prefill CUDA graphs: BF16
weights, native KV dtype, FlashInfer attention, 4096-token chunks, four running
requests, and a 1,048,576-token KV pool limit. Mamba uses `no_buffer` radix caching,
page size 1 and overlap scheduling disabled in both modes. Disaggregation uses
NIXL/UCX and the eight InfiniBand interfaces. The image contains Mamba state
transfer support; actual serving validation is recorded in the benchmark report.

## Test the LoadBalancer

```bash
curl http://<LOADBALANCER_IP>:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
       "messages":[{"role":"user","content":"Explain prefill and decode in three sentences."}],
       "max_tokens":256,"temperature":0,
       "chat_template_kwargs":{"enable_thinking":false}}'
```

The benchmark uses NVIDIA's `enable_thinking=false` chat-template setting and
native tokenizer, not DeepSeek's Python encoder. See the pinned
[NVIDIA model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/blob/bf77c3174f68ad409e1c2aa60daeb46e32d1c606/README.md)
for the model's SGLang recipe and request options.

## Benchmark files

- `benchmark_128k.py`: runs three repeats of the fixed 32-session comparison cohort for one mode.
- `benchmark_8k_128k.py`: 8K-in / 128K-out waves for the TP4 layouts (with `51-benchmark-client-long-decode.yaml`,
  `deployment-tp4*.json` and `benchmarks.long_decode`).
- `clear_cache.py`: requires acknowledged cache resets on every worker (`clear_cache.py MODE 4` for TP4).
- `50-benchmark-client.yaml`: a CPU client that persists artifacts under
  `.benchmarks/nemotron128k` on `model-0`.
- `deployment.json` / `deployment-disaggregated.json`: mode-specific run metadata.
- [Analysis notebook](../../../studies/nemotron-3-nano-128k-comparison/nemotron_3_nano_128k.ipynb): reads saved
  results without contacting the cluster.

The benchmark report contains dataset generation, client setup and analysis steps.
