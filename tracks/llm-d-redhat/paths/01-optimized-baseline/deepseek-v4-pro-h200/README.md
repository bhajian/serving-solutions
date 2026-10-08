# DeepSeek V4 Pro on H200: path 01 instance

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [llm-d + Red Hat AI](../../../README.md) › [Paths](../../README.md) › [01 · Optimized baseline](../README.md) › deepseek-v4-pro-h200

> **Deployed 2026-10-08, study running.** Red Hat validates `RedHatAI/DeepSeek-V4-Pro`
> (the preview weights), not the 0813 checkpoint served here.

Four aggregated vLLM replicas (TP8, one per H200 node, 32 GPUs) behind the llm-d router, on
the Nebius H200 cluster ([platform/sites](../../../../../platform/sites/README.md)).

| Layer | Version |
| --- | --- |
| Model | `deepseek-ai/DeepSeek-V4-Pro-0813` @ `72e1d3230f6c080a530b0a1d46f8eb4602340597` (893 GB, MXFP4 experts) |
| Engine | `registry.redhat.io/rhaii-fast/vllm-cuda-rhel9:3.6.0-fast.1` (vLLM 0.26.0, CUDA 13.0.2, UID 1001), pinned by digest |
| Router | llm-d v0.10.0: chart `llm-d-router-standalone` v0.11.0, EPP v0.11.0, Envoy sidecar |
| CRDs | Gateway API Inference Extension v1.5.0 (`InferencePool`) |

| File | Objects |
| --- | --- |
| [modelserver.yaml](modelserver.yaml) | Headless Service and StatefulSet `deepseek-v4-pro`: weight check (init), vLLM on :8000, 8 GPUs, one `weights-deepseek-v4-pro-N` claim per replica |
| [copy-weights.yaml](copy-weights.yaml) | Claims for replicas 2 and 3 and Jobs that fill them from replicas 0 and 1's disks, verified by file count and bytes |
| [kustomization.yaml](kustomization.yaml) | Namespace `llm-d` and the labels the router selects |
| [router/values.yaml](router/values.yaml) | Router values shared by every arm |
| `router/arm-*.yaml`, `router/rendered-*.yaml` | One scheduler per arm of the [routing study](../../../studies/deepseek-v4-pro-256k-routing/README.md), and the rendered chart for each |

## Engine flags

They follow the vLLM recipe's Hopper lane, with a 262,144-token window for 256K prompts:

- **No expert parallelism.** MXFP4 Marlin with EP hits an illegal memory access on Hopper
  ([vllm#47769](https://github.com/vllm-project/vllm/issues/47769)). Plain TP8 instead.
- **No speculative decoding.** DSpark on SM90 sparse attention landed in vLLM 0.29.
- `--enable-prompt-tokens-details` returns `cached_tokens` per request;
  `VLLM_SERVER_DEV_MODE=1` exposes `POST /reset_prefix_cache` for benchmark resets (ClusterIP only).

## Weights

The cluster has only RWO network SSDs (no shared filesystem, no snapshots), so each replica
owns a 1500Gi disk with its own copy. Replicas 0 and 1 reuse the disks from the Dynamo
studies; [copy-weights.yaml](copy-weights.yaml) fills replicas 2 and 3. Each copy pod runs on
its source replica's node, because an RWO disk can be mounted by several pods on one node.
Measured: about 320 MB/s per copy (≈ 45 min) and about 400 MB/s per replica load (≈ 35 min).

## Deploy

```bash
export KUBE_CONTEXT=<context>
cd tracks/llm-d-redhat/paths/01-optimized-baseline/deepseek-v4-pro-h200
# once: install steps 1–3 (pull secret, CRDs): ../../../install/README.md
# weight claims for replicas 0 and 1 bound to existing disks, or download Jobs; then:
kubectl --context "$KUBE_CONTEXT" -n llm-d apply -f copy-weights.yaml      # fills disks 2 and 3
kubectl --context "$KUBE_CONTEXT" apply -k .                                # StatefulSet, 4 replicas
kubectl --context "$KUBE_CONTEXT" -n llm-d apply -f router/rendered-optimized-baseline.yaml
```

Refresh a rendered router file without a local Helm install:

```bash
docker run --rm -v "$PWD:/w" -w /w alpine/helm:3.18.4 template llmd \
  oci://ghcr.io/llm-d/charts/llm-d-router-standalone --version v0.11.0 \
  --namespace llm-d -f router/values.yaml -f router/arm-optimized-baseline.yaml > router/rendered-optimized-baseline.yaml
```

## Verify through the router

```bash
kubectl --context "$KUBE_CONTEXT" -n llm-d port-forward service/llmd-epp 8000:80
curl -fsS http://127.0.0.1:8000/v1/models
curl --fail-with-body --max-time 600 http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-ai/DeepSeek-V4-Pro-0813","messages":[{"role":"user","content":"Explain prefill and decode briefly."}],"max_tokens":256,"chat_template_kwargs":{"thinking":false}}'
```

## Clean up

```bash
kubectl --context "$KUBE_CONTEXT" -n llm-d delete -f router/rendered-optimized-baseline.yaml
kubectl --context "$KUBE_CONTEXT" delete -k .
```

Claims, disks and the cluster-scoped CRDs remain. Disks 0 and 1 use reclaim policy `Retain`;
disks 2 and 3 were dynamically provisioned with `Delete`.
