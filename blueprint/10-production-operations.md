# 10 · Production operations

[Home](../README.md) › [Blueprint](README.md) › 10 · Production operations

**Executive summary.** What changes between the lab path that produced `tracks/nvidia-dynamo/studies/` and production, row by row, and where the production overlay implements each change: gateway with TLS, OIDC and rate limits; NetworkPolicies; operator-managed rollouts; RDMA via device plugin; observability and alerts; and the validation gates before go-live. The production overlay is UNVALIDATED on hardware.

| What you get from this repository | What you still own |
| --- | --- |
| Production overlay, observability stack, troubleshooting runbook and experiments for each gate | Running the gates, on-call and incident response |

The lab deployments that produced `tracks/nvidia-dynamo/studies/` are deliberately transparent: hand-written Deployments, a single etcd, host networking and per-node weights. The production overlay implements every row of the table below as manifests (UNVALIDATED on hardware). The per-row diff is in [tracks/nvidia-dynamo/LAB-VS-PRODUCTION.md](../tracks/nvidia-dynamo/LAB-VS-PRODUCTION.md).

## From lab to production

| Area | Reference deployment (lab / PoC) | Production |
|---|---|---|
| Orchestration | Plain Deployments / Compose | Dynamo operator (`DynamoGraphDeployment` + Grove) or llm-d Helm guides, with coordinated rollouts and gang scheduling |
| Scaling | Fixed 1 prefill : 1 decode, or N replicas | SLO-driven autoscaling per pool (Dynamo Planner, llm-d variant autoscaler), sized by [chapter 09](09-parallelism-and-sizing.md) |
| Discovery | Single etcd, no TLS | Kubernetes API (Dynamo 1.4.0 operator default), no etcd ([tracks/nvidia-dynamo/install](../tracks/nvidia-dynamo/install/)) |
| API security | Plain HTTP on :8000, private network | TLS and authentication at a gateway, per-tenant quotas and rate limits, no public worker or discovery ports |
| Network | `hostNetwork`, firewall-scoped | Host networking only where RDMA needs it; NetworkPolicies and host firewalls for east-west ports |
| RDMA access | `privileged: true` + `/dev/infiniband` | NVIDIA Network Operator with an RDMA device plugin (shared or SR-IOV); unprivileged pods with `IPC_LOCK` |
| GPU stack | Host-installed drivers | NVIDIA GPU Operator: pinned driver, device plugin, DCGM exporter, GDS when offloading |
| Weights | `hostPath`, downloaded per node | Read-only shared volume on a fast file system, or pre-staged NVMe managed by a job; revision verified at startup |
| Images | Dynamo vLLM pinned by digest, others by tag | **Every** image pinned by digest, mirrored, scanned and promoted through environments |
| Rollouts | Stop both roles, then start both | Operator-coordinated rollouts; blue/green at the gateway for model upgrades |
| Reliability | One worker per role | N+1 per role across failure domains; replicated frontends |
| Data | Benchmark logs keep prompts and outputs | Retention policy for prompts, outputs and **cached KV** ([principle 13](02-design-principles.md#13-protect-cached-state-like-data)) |

## SLOs

Define SLOs per phase, because each phase maps to a pool you can scale:

| SLO | Measures | Scaled by |
|---|---|---|
| **p99 TTFT** | Queueing + prefill + KV transfer + first decode step | Prefill pool, router, KV reuse |
| **p99 ITL / TPOT** | Decode step time under load | Decode pool, batch limits |
| **Availability** | Successful responses / requests | Replicas per role, failure domains |
| **Goodput** | Requests meeting *both* latency SLOs per second | P:D ratio and total capacity |

## Observability

| Signal | Source | Why |
|---|---|---|
| TTFT, ITL, e2e latency, tokens/s | Frontend/router metrics, client benchmarks | The SLOs themselves |
| Queue depth per pool | Frontend, EPP, engine scheduler metrics | Which pool to scale |
| KV-cache usage and hit rate (per tier) | Engine metrics, KV router / KVBM, EPP | Routing quality, offload value |
| **KV transfer latency, bytes, errors** | NIXL / engine connector metrics | Health of the disaggregation edge |
| InfiniBand port counters, errors | `/sys/class/infiniband/*/counters`, fabric manager | Rails actually used, no drops |
| GPU utilization, memory, power, XID errors | DCGM exporter | Hardware health, saturation |
| Worker health | `/health` and `/live` on the system port (`:9090` in the operator graphs, `:8081` in the lab) | Readiness and startup |

The PodMonitors, alert rules (SLO burn, transfer latency, XID, queue growth, prefill host memory, missing workers) and Grafana dashboard are in [tracks/nvidia-dynamo/observability](../tracks/nvidia-dynamo/observability/).

**Health probes:** keep a long startup window (large checkpoints load for tens of minutes) and **no aggressive liveness probe**, so a long prefill never gets a worker killed. Add synthetic end-to-end probes through the public endpoint. The operator graphs use a 2 h startup window, a lenient liveness probe (6 × 30 s), a frontend readiness check that requires discovered workers, and a canary CronJob through the gateway.

## Security

- Never expose discovery (2379), worker (8081/9090, 5600, 8998, 30000) or engine ports outside the serving network. The production namespaces start from default-deny NetworkPolicies.
- Terminate TLS and authenticate at the gateway. Consider mTLS for east-west control traffic.
- Keep secrets such as registry and Hugging Face tokens in a secret store, never in manifests or run records. The reference tools read tokens from the environment only.
- Treat prefix sharing across tenants, offloaded KV and shared KV storage as tenant data: isolate, encrypt and expire it.

## Validation gates before go-live

1. **RDMA proven:** `ib_write_bw` on every rail, and NIXL transfers visible in metrics and IB counters under load.
2. **Functional:** chat, streaming, tool calls and reasoning fields validated against client applications.
3. **Performance:** a sweep on representative traces meets p99 TTFT and ITL at target load, with 3 or more repetitions.
4. **Resilience:** kill a decode worker, a prefill worker and a frontend in turn. Measure impact and recovery.
5. **Soak:** 24 hours or more at expected load with no memory growth, transfer errors or XID events.
6. **Runbook:** [reference/troubleshooting.md](../reference/troubleshooting.md), adapted to the environment, is handed to operations.

---

**Next:** [11 · Decision guide](11-decision-guide.md)
