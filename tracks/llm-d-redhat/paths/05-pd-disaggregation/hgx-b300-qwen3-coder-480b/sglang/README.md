# 07 · llm-d + SGLang 0.5.20 · Kubernetes

[Home](../../../../../../README.md) › [Tracks](../../../../../README.md) › [llm-d + Red Hat AI](../../../../README.md) › [Paths](../../../README.md) › [05 · P/D disaggregation](../../README.md) › [hgx-b300-qwen3-coder-480b](../README.md) › SGLang 0.5.20

## What you deploy

| File | Objects | Runs on |
|---|---|---|
| [namespace.yaml](namespace.yaml) | Namespace `llm-d` (privileged) | n/a |
| [prefill.yaml](prefill.yaml) | Deployment `prefill`: engine on :8000, 8 GPUs | node `prefill-node` |
| [decode.yaml](decode.yaml) | Deployment `decode`: engine on :8200 plus routing sidecar on :8000 | node `decode-node` |
| [kustomization.yaml](kustomization.yaml) | namespace + workers (not the router) | n/a |
| [router/values.yaml](router/values.yaml) | Helm values for the llm-d router: P/D filters, fail-closed | n/a |
| [router/rendered.yaml](router/rendered.yaml) | Snapshot of the rendered chart, for review | n/a |
| [deployment.json](deployment.json) | Run record for benchmarks | n/a |

With SGLang, the sidecar uses `--kv-connector=sglang` and the bootstrap port 8998 on the prefill node must be reachable from Node B. The pinned llm-d SGLang guide documents limitations in cleaning up cancelled requests, so watch for them.

## Before you start

- [ ] [00 · Prerequisites](../../../../../../platform/prerequisites/) done, with **Qwen3-Coder-480B-A35B-Instruct-FP8** downloaded to `/data/models/qwen-480b` on both nodes:

  ```bash
  python tools/download_model.py --model qwen-480b      # on each node
  ```

- [ ] Kubernetes **1.33+**, `helm` 3 with OCI support, and RDMA working inside privileged pods.
- [ ] **Edit the node-specific values**, because these generated files hard-code them:

  ```bash
  grep -n "kubernetes.io/hostname\|10.104" tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang/prefill.yaml tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang/decode.yaml
  ```

  Replace `prefill-node` and `decode-node` with your node names, and `<B300_NODE_A_IP>` and `<B300_NODE_B_IP>` with the nodes' private IPs. Alternatively, edit `configs/cluster.yaml` and regenerate with `python tools/render.py --target llmd --backend sglang --model qwen-480b --out tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang`.
- [ ] No Dynamo track is running on these GPUs.

## Step 1 · Install the InferencePool CRD (once per cluster)

```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/v1.5.0/v1-manifests.yaml
```

## Step 2 · Namespace and workers

```bash
kubectl apply -f tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang/namespace.yaml
kubectl apply --dry-run=server -k tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang
kubectl apply -k tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang
kubectl -n llm-d get pods -o wide
kubectl -n llm-d logs -f deployment/prefill -c modelserver
kubectl -n llm-d logs -f deployment/decode  -c modelserver     # second terminal
kubectl -n llm-d rollout status deployment/prefill --timeout=120m
kubectl -n llm-d rollout status deployment/decode  --timeout=120m
```

## Step 3 · Router (Helm)

```bash
bash tools/llmd-router.sh render tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang     # optional: refresh router/rendered.yaml and review it
bash tools/llmd-router.sh install tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang    # helm upgrade --install, pinned chart v0.11.0
kubectl -n llm-d logs deployment/decode -c routing-proxy --tail=50
```

Install the chart with Helm **or** apply `router/rendered.yaml`, not both. Router fail-open is disabled, so a scheduling failure never silently becomes an aggregated run.

## Step 4 · Verify through the router

```bash
kubectl -n llm-d port-forward service/llmd-epp 8000:80
curl -fsS http://127.0.0.1:8000/v1/models
curl --fail-with-body --max-time 300 http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8","messages":[{"role":"user","content":"Explain prefill and decode briefly."}],"max_tokens":128}'
```

Always test and benchmark **through the router**. Calling the prefill engine directly bypasses P/D. To confirm transfers, watch `http://<node-a-ip>:8000/metrics` and `http://<node-b-ip>:8200/metrics`, the sidecar logs and the InfiniBand port counters, as in step 7 of the [Dynamo guides](../../../../../nvidia-dynamo/sites/hgx-b300-2x8/02-dynamo-disagg-vllm/KUBERNETES.md#step-7--prove-the-kv-cache-really-moves-over-infiniband).

## Step 5 · Benchmark

Use `--technology llmd-k8s --deployment tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang/deployment.json` and the **router** URL. See [benchmarks/README.md](../../../../../../benchmarks/README.md). The pinned chart has a 1000-second ext-proc message timeout, so test your largest prompt end to end.

## Clean up

```bash
helm uninstall llmd -n llm-d
kubectl delete -k tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/sglang
```

The shared CRDs and the model data on the nodes remain.
