# Production overlay

[Home](../../../README.md) › [Tracks](../../README.md) › [NVIDIA Dynamo](../README.md) › Production

> **UNVALIDATED — scheduled.** Every object here renders with `kustomize build` and
> passes strict schema validation against Dynamo 1.4.0, Kubernetes 1.33, Gateway API
> v1.3.0, Envoy Gateway v1.4.2 and cert-manager v1.17.2 (`tools/validate.py`). It has not
> been applied to a cluster. First run: [tracks/nvidia-dynamo/studies/planned/00-site-migration](../studies/planned/00-site-migration/).

**What you get:** for each model on the H200 site, an aggregated and a disaggregated
graph with site patches; a namespace bundle with Pod Security labels, default-deny
NetworkPolicies, a weights PVC and staging Job, an HTTPRoute, JWT/OIDC auth and
per-tenant rate limits; a Planner (disaggregated) and its profiling request; and a shared
TLS Gateway. **What you still own:** the identity provider, DNS and certificate issuer,
a ReadWriteMany storage class, tenant limits, the SLO targets, and running the profiling
request.

| Path | Contents |
| --- | --- |
| [gateway/](gateway/) | `GatewayClass` (Envoy), `Gateway` `inference` (HTTPS 443, routes only from namespaces labelled `serving-solutions/expose`), cert-manager `Certificate` |
| `<model>-h200/namespace/` | Namespace, NetworkPolicies, `model-weights` RWX PVC, `stage-weights` Job, planner profiling PVC, `HTTPRoute`, `SecurityPolicy` (JWT; `auth-api-key.alternative.yaml` for API keys), `BackendTrafficPolicy` |
| `<model>-h200/aggregated/` | Base graph + RDMA resource, `UCX_NET_DEVICES`, H200 node selector, KAI queue |
| `<model>-h200/disaggregated/` | As above + Planner component (SLA mode) and its config |
| `<model>-h200/profiling/` | `DynamoGraphDeploymentRequest` (thorough SLA profiling, `autoApply: false`) |
| [operators/](../../../platform/operators/) | NVIDIA GPU Operator and Network Operator Helm values |

## Apply order

```bash
python tools/render_site.py --env platform/site.env tracks/nvidia-dynamo/production --out build/site
K="kubectl --context $KUBE_CONTEXT"
$K apply -k build/site/production/gateway
$K apply -k build/site/production/nemotron-3-nano-h200/namespace
$K -n nemotron-3-nano create secret generic hf-token --from-literal=HF_TOKEN="$HF_TOKEN"
$K -n nemotron-3-nano wait --for=condition=complete job/stage-weights --timeout=2h
$K apply -k build/site/production/nemotron-3-nano-h200/aggregated      # or disaggregated
```

The Planner component reads profiling data from the `<model>-planner-profiling` PVC.
It fails to start until the profiling request has run (tracks/nvidia-dynamo/studies/planned/03).

## SLO targets and the Planner

The example targets are design guidance, not measured results. The 1.4.0 Planner
compares the **mean** TTFT and ITL from Prometheus histograms
(`planner/monitoring/traffic_metrics.py` L208), not p99. The p99 objectives (Nemotron:
TTFT 2 s, ITL 40 ms) are therefore entered as tighter mean targets (1 s, 25 ms) in
`planner_config.json`. Goodput at p99 is what [benchmarks/](../../../benchmarks/) reports.
There is no per-role replica cap in 1.4.0; `max_gpu_budget: 16` bounds the whole graph.
