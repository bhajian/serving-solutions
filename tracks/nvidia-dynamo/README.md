# Track 1 · NVIDIA Dynamo

[Home](../../README.md) › [Tracks](../README.md) › NVIDIA Dynamo

**Executive summary.** Dynamo 1.4.0 with SGLang (measured) and vLLM (reference). Two ways to
deploy. The **production path** is operator-managed: DynamoGraphDeployments
([graphs/](graphs/README.md)) composed with a production overlay ([production/](production/README.md))
that adds the gateway, TLS and auth, NetworkPolicies, RDMA via device plugin, the Planner and
observability; it is **UNVALIDATED** on hardware. The **lab path** is the hand-written
manifests that produced every measured result, kept unchanged under each site profile's
`lab/` folder. How the two differ: [LAB-VS-PRODUCTION.md](LAB-VS-PRODUCTION.md).

| Folder | Contents | Status |
| --- | --- | --- |
| [install/](install/README.md) | dynamo-platform 1.4.0 Helm values: Kubernetes discovery, Grove + KAI, cert-manager webhook | UNVALIDATED |
| [common/](common/README.md) | Kustomize component shared by every graph: discovery-aware frontend probe, GC hook | UNVALIDATED |
| [graphs/](graphs/README.md) | One `nvidia.com/v1beta1` DynamoGraphDeployment per model, aggregated and disaggregated variants (generated) | UNVALIDATED |
| [production/](production/README.md) | Gateway, auth, rate limits, NetworkPolicies, Planner, profiling, per-model namespace bundles (generated) | UNVALIDATED |
| [observability/](observability/README.md) | PodMonitors, alert rules, Grafana dashboard, canary (generated) | UNVALIDATED |
| [sites/](sites/README.md) | Per-site model profiles: the H200 lab manifests as measured; the B300 reference tracks and their Compose twins | H200 **validated** (lab path); B300 reference |
| [studies/](studies/README.md) | Completed studies with data, notebooks and reports; `planned/` experiments | 3 complete, 10 planned |

## Deploy (production path)

Site values (node names, addresses, kube context, domains, storage classes) are never
committed. Copy [platform/site.env.example](../../platform/site.env.example) to `platform/site.env`,
then render; rendered files mirror their repository path under `build/site/`:

```bash
python tools/render_site.py --env platform/site.env tracks platform --out build/site
kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/production/nemotron-3-nano-h200/aggregated
```

Order for a new cluster: [operator](install/README.md) → [GPU and Network Operators](../../platform/operators/README.md) →
[observability](observability/README.md) → [gateway](production/gateway/) → a model's `namespace/` bundle →
its `aggregated/` or `disaggregated/` graph. [Planned study 00](studies/planned/00-site-migration/README.md)
walks the H200 site through exactly this.

## Generated folders

`graphs/`, `production/` (except its README), `observability/` and `studies/planned/` are
written by generators in [tools/](../../tools/README.md); tests fail when they drift. Edit the
generator, then rerun it:

```bash
python tools/render_graphs.py && python tools/render_production.py
python tools/render_observability.py && python tools/render_experiments.py
```
