# Nemotron 3 Nano — lab overlay

[Home](../../../../../../README.md) › [Tracks](../../../../../README.md) › [NVIDIA Dynamo](../../../../README.md) › [Sites](../../../README.md) › [nebius-h200-2x8](../../README.md) › [nemotron-3-nano](../README.md) › Lab

> **Lab path.** Hand-written Deployments with `hostNetwork`, privileged-equivalent
> capabilities (`IPC_LOCK`, `SYS_RESOURCE`) and a single etcd, exactly as measured.
> Topology changes mean applying a different worker set. The production path is the
> operator-managed DynamoGraphDeployment in [tracks/nvidia-dynamo/graphs](../../../../graphs/), where a
> topology change is an edit of one custom resource.

- [as-measured/](as-measured/) holds the manifests that produced the results in
  `tracks/nvidia-dynamo/studies/`, unchanged, one folder per file so they can be composed.
- [common/](common/) is a Kustomize Component that places every variant in the
  `nemotron-3-nano` namespace and rewrites in-cluster endpoints accordingly.
- Each variant below adds the shared PVC claims from
  [storage/](../../../../../../platform/sites/nebius-h200-2x8/storage/).

| Variant | Deploy |
| --- | --- |
| [benchmark-client-128k](benchmark-client-128k/) | `kubectl apply -k` after `render_site.py` |
| [benchmark-client-8k-128k](benchmark-client-8k-128k/) | `kubectl apply -k` after `render_site.py` |
| [model-download](model-download/) | `kubectl apply -k` after `render_site.py` |
| [tp4-aggregated](tp4-aggregated/) | `kubectl apply -k` after `render_site.py` |
| [tp4-disaggregated](tp4-disaggregated/) | `kubectl apply -k` after `render_site.py` |
| [tp8-aggregated](tp8-aggregated/) | `kubectl apply -k` after `render_site.py` |
| [tp8-disaggregated](tp8-disaggregated/) | `kubectl apply -k` after `render_site.py` |

```bash
python tools/render_site.py --env platform/site.env tracks/nvidia-dynamo/sites/nebius-h200-2x8 --out build/site
kubectl --context "$KUBE_CONTEXT" apply -k build/site/nebius-h200-2x8/nemotron-3-nano/lab/tp8-disaggregated
```
