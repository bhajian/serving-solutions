# Overlays: lab versus production

[Home](../../README.md) › [Tracks](../README.md) › [NVIDIA Dynamo](README.md) › Overlays

| Concern | [Lab](sites/) (as measured) | [Production](production/) (operator path) |
| --- | --- | --- |
| Status | Validated: produced every result in `tracks/nvidia-dynamo/studies/` | **UNVALIDATED — scheduled** ([experiments](studies/planned/)) |
| Workload objects | Hand-written Deployments per worker | One `DynamoGraphDeployment` (v1beta1) per model, reconciled by the Dynamo operator |
| Topology change | Apply a different worker Deployment set | Apply the other variant: one custom-resource edit, same graph name |
| Rollout | Stop and restart both roles by hand | Operator-coordinated; Grove PodCliqueSet update strategy |
| Discovery | Single etcd, no TLS | Kubernetes API (operator default in 1.4.0); no etcd, no NATS |
| Gang scheduling | None | Grove + KAI scheduler queue annotation |
| Frontend | 1 replica, `/health` readiness (200 even with no workers) | 2 replicas, router state sync, readiness/liveness that require discovered workers |
| Router | KV router (default weights), later round-robin | KV router with active-request weighting and a wait for all workers |
| Networking | `hostNetwork`, host ports per worker | Pod network; Gateway API + Envoy with TLS, JWT/OIDC auth, per-tenant rate limits; default-deny NetworkPolicies |
| RDMA | `hostNetwork` + `IPC_LOCK` + `SYS_RESOURCE` | RDMA shared device plugin resource + `IPC_LOCK`; no hostNetwork, no privileged |
| Placement | `kubernetes.io/hostname` per worker | `nvidia.com/gpu.product` node selector; operator spreads replicas |
| Weights | Per-node RWO disks, downloaded by Job | ReadWriteMany PVC staged once, `SHA256SUMS` + `DEPLOYED_REVISION`, verified by an init container |
| Host memory | Request 96Gi / limit 384Gi for every TP4 worker | Per role; prefill limit 448Gi against a 308 GiB observed peak, plus a prefill concurrency cap |
| GC pauses | Python defaults | `--gc-threshold 7000 10 100`; opt-in `gc.freeze()` after warmup |
| Autoscaling | None | Dynamo Planner (SLA mode) on disaggregated graphs |
| Images | sglang-runtime by digest; busybox by tag | Every image by digest |
| Observability | Prometheus scrapes by hand | ServiceMonitors/PodMonitors, alert rules, dashboards ([tracks/nvidia-dynamo/observability](observability/)) |

Render both sides for a site and compare:

```bash
python tools/render_site.py --env platform/site.env deploy --out build/site
diff <(kustomize build build/site/tracks/nvidia-dynamo/sites/nebius-h200-2x8/nemotron-3-nano/lab/tp4-disaggregated) \
     <(kustomize build build/site/tracks/nvidia-dynamo/production/nemotron-3-nano-h200/disaggregated)
```
