# DeepSeek V4 Pro — lab overlay

[Home](../../../../../../README.md) › [Tracks](../../../../../README.md) › [NVIDIA Dynamo](../../../../README.md) › [Sites](../../../README.md) › [nebius-h200-2x8](../../README.md) › [deepseek-v4-pro](../README.md) › Lab

> **Lab path.** Hand-written Deployments with `hostNetwork`, privileged-equivalent
> capabilities (`IPC_LOCK`, `SYS_RESOURCE`) and a single etcd, exactly as measured.
> Topology changes mean applying a different worker set. The production path is the
> operator-managed DynamoGraphDeployment in [tracks/nvidia-dynamo/graphs](../../../../graphs/), where a
> topology change is an edit of one custom resource.

- [as-measured/](as-measured/) holds the manifests that produced the results in
  `tracks/nvidia-dynamo/studies/`, unchanged, one folder per file so they can be composed.
- [common/](common/) is a Kustomize Component that places every variant in the
  `deepseek-v4-pro` namespace and rewrites in-cluster endpoints accordingly.
- Each variant below adds the shared PVC claims from
  [storage/](../../../../../../platform/sites/nebius-h200-2x8/storage/).

| Variant | Deploy |
| --- | --- |
| [aggregated](aggregated/) | `kubectl apply -k` after `render_site.py` |
| [disaggregated](disaggregated/) | `kubectl apply -k` after `render_site.py` |
| [model-download](model-download/) | `kubectl apply -k` after `render_site.py` |

```bash
python tools/render_site.py --env platform/site.env tracks/nvidia-dynamo/sites/nebius-h200-2x8 --out build/site
kubectl --context "$KUBE_CONTEXT" apply -k build/site/nebius-h200-2x8/deepseek-v4-pro/lab/model-download
```
