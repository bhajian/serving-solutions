# Dynamo operator (platform 1.4.0)

[Home](../../../README.md) › [Tracks](../../README.md) › [NVIDIA Dynamo](../README.md) › Operator

> **UNVALIDATED — scheduled.** Install steps and values are checked offline against
> the pinned chart (`tests/test_operator_values.py`); the install has not been run on
> the H200 site. It is step 2 of [tracks/nvidia-dynamo/studies/planned/00-site-migration](../studies/planned/00-site-migration/).

**What you get:** pinned Helm values for the `dynamo-platform` 1.4.0 chart, which
installs the Dynamo operator and its CRDs (DynamoGraphDeployment,
DynamoGraphDeploymentRequest, and others). **What you still own:** cert-manager,
kube-prometheus-stack, the GPU and Network Operators, and Grove/KAI upgrades.

| File | Use |
| --- | --- |
| [values-production.yaml](values-production.yaml) | Kubernetes-API discovery (no etcd, no NATS); Grove and KAI installed separately and enabled; cert-manager-managed webhook with `failurePolicy: Fail`; Prometheus endpoint for the Planner; operator image pinned by digest |
| [values-lab.yaml](values-lab.yaml) | Test clusters: Grove and KAI as bundled subcharts |

## Install

```bash
export NAMESPACE=dynamo-system
# 1. Prerequisites (versions as validated by upstream for 1.4.0; pin your own):
#    cert-manager, kube-prometheus-stack (release name "prometheus" in "monitoring"),
#    NVIDIA GPU Operator and Network Operator (see ../prerequisites and
#    ../overlays/production/operators).

# 2. Grove and KAI scheduler, at the versions dynamo-platform 1.4.0 pins
#    (reference/upstream/dynamo-v1.4.0/platform-Chart.yaml):
helm upgrade --install grove oci://ghcr.io/ai-dynamo/grove/grove-charts \
  --version v0.1.0-alpha.12-rc1 -n grove-system --create-namespace      # TODO(verify-upstream): OCI chart path
helm upgrade --install kai-scheduler oci://ghcr.io/kai-scheduler/kai-scheduler/kai-scheduler \
  --version v0.13.4 -n kai-scheduler --create-namespace                  # TODO(verify-upstream): OCI chart path

# 3. Dynamo platform (operator + CRDs):
helm fetch https://helm.ngc.nvidia.com/nvidia/ai-dynamo/charts/dynamo-platform-1.4.0.tgz
helm upgrade --install dynamo-platform dynamo-platform-1.4.0.tgz -n "$NAMESPACE" --create-namespace \
  -f tracks/nvidia-dynamo/install/values-production.yaml
kubectl get crd | grep -E 'dynamographdeployments|dynamographdeploymentrequests'
```

The NGC URL above is the one in the 1.4.0 release notes (`docs/fern/assets/releases.json`).
It returned HTTP 404 when checked on 2026-10-01 (`TODO(verify-upstream)`). If it is still
unavailable, build the chart from the pinned tag:
`git clone --branch v1.4.0 https://github.com/ai-dynamo/dynamo && helm dependency build dynamo/deploy/helm/charts/platform`.

## Why gang scheduling (Grove + KAI)

A disaggregated graph is only useful when its prefill and decode pools both exist,
and a multinode TP worker is only useful when every rank is placed. Default
Kubernetes scheduling places pods one at a time. Under GPU pressure it can start half
of a graph and hold its GPUs indefinitely while the rest stays Pending. With Grove
enabled, the operator reconciles every DynamoGraphDeployment as a Grove PodCliqueSet
(`dynamographdeployment_controller.go` L441-473). Its cliques are scheduled as a unit
by KAI, so partial placement does not happen. Multinode components fail outright
without Grove or LWS (L430-435). Upstream pins Grove at **v0.1.0-alpha.12-rc1**, an
alpha release, so treat gang scheduling as a feature to qualify on your cluster.

The production overlays label each graph with a KAI queue
(`nvidia.com/kai-scheduler-queue`). The queue must exist before the graph is applied
(upstream `multinode-deployments.md` L58).

## Discovery: why there is no etcd here

The operator default (`discoveryBackend: kubernetes`) registers workers through the
Kubernetes API instead of etcd leases. The lab deployment used a single etcd, and its
watch failure ("channel closed") dropped every worker from the frontend while all pods
stayed Ready (see [reference/troubleshooting.md](../../../reference/troubleshooting.md)).
The production path removes that dependency rather than making etcd highly available.
If you must use etcd (`nvidia.com/dynamo-discovery-backend: etcd`), run a three-member
etcd with TLS and authentication; that variant is not provided here.
