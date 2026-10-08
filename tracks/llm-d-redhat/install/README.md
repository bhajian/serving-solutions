# Install: once per cluster

[Home](../../../README.md) › [Tracks](../../README.md) › [llm-d + Red Hat AI](../README.md) › Install

Everything a well-lit path needs before its own manifests. GPU drivers, device plugin, RDMA and
storage are in [platform/](../../../platform/README.md).

## 1 · Red Hat AI Inference Server image

| Image | vLLM | Use |
| --- | --- | --- |
| `registry.redhat.io/rhaii-fast/vllm-cuda-rhel9:3.6.0-fast.1` (digest `sha256:5f1fb3f2…0195f`) | 0.26.0 (`0.26.0+rhaiv.8`) | **Path 01.** The only Red Hat build new enough for DeepSeek V4 Pro 0813 (vLLM ≥ 0.25) |
| `registry.redhat.io/rhaii/vllm-cuda-rhel9:3.5.x` | 0.24.0 (3.5.0) | Models supported by vLLM 0.24; DeepSeek V4 needs `--kv-cache-dtype fp8` on 3.5.0 |
| `registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.x` | 0.13.0 | Older models only |

What the image does by default, and what path 01 changes:

| Default | Effect | Path 01 |
| --- | --- | --- |
| Runs as UID 1001, GID 0 | Model files must be world- or group-0-readable | Init container checks readability before vLLM starts |
| Entrypoint `python3 -m vllm.entrypoints.openai.api_server`, port 8000 | Matches the InferencePool target port | Unchanged |
| `HF_HUB_OFFLINE=1` | No downloads at startup | Weights come from a PVC |
| Usage statistics sent to `console.redhat.com` | Outbound telemetry | `DO_NOT_TRACK=1` |
| CUDA 13.0.2 | Needs a matching driver | Nebius nodes use the `cuda13.0` driver preset |

## 2 · Pull secret

Use a **registry service account**, not a personal login: access.redhat.com →
[Registry Service Accounts](https://access.redhat.com/terms-based-registry/) → New Service
Account. The username looks like `1234567|name`; the token is a JWT of several hundred
characters. Copy it with the page's copy button, then create the secret without the token
touching shell history:

```bash
RH_TOKEN="$(pbpaste | tr -d '[:space:]')"          # macOS; or: read -rs RH_TOKEN, paste, Enter
kubectl --context "$KUBE_CONTEXT" -n llm-d create secret docker-registry rh-registry \
  --docker-server=registry.redhat.io --docker-username='1234567|name' \
  --docker-password="$RH_TOKEN" --dry-run=client -o yaml | kubectl --context "$KUBE_CONTEXT" apply -f -
unset RH_TOKEN
```

Check it without printing the token: a `401` from Red Hat's token endpoint means the token
was truncated. The token length should be several hundred characters and start with `eyJ`.

## 3 · Gateway API Inference Extension CRDs

```bash
kubectl --context "$KUBE_CONTEXT" apply -f https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/v1.5.0/v1-manifests.yaml
```

Standalone router mode (below) needs only the `InferencePool` CRD. Gateway mode also needs the
Gateway API CRDs (v1.5.1) and a GAIE-capable gateway (Istio, agentgateway, GKE); Cilium's
gateway is not one.

## 4 · Router

Chart `oci://ghcr.io/llm-d/charts/llm-d-router-standalone` v0.11.0: endpoint picker (EPP) and
an Envoy sidecar in one pod, an `InferencePool`, and a ClusterIP Service on port 80. Each path
keeps its values in `router/` and a rendered copy, so no local Helm is required:

```bash
docker run --rm -v "$PWD:/w" -w /w alpine/helm:3.18.4 template llmd \
  oci://ghcr.io/llm-d/charts/llm-d-router-standalone --version v0.11.0 \
  --namespace llm-d -f router/values.yaml -f router/arm-<name>.yaml > router/rendered-<name>.yaml
```

Two router defaults matter for every path (from the v0.11.0 source):

- The router silently adds a load filter (`utilization-detector`) to every scheduling profile,
  dropping pods at KV usage ≥ 0.8 or queue ≥ 5. Long prompts trip it. Path 01 sets the same
  neutral thresholds in every arm so that comparisons measure the scheduler alone.
- Metrics on `:9090` require a bearer token by default; `--metrics-endpoint-auth=false`
  (values `router.epp.flags`) lets an in-cluster client scrape `llm_d_epp_*`.
