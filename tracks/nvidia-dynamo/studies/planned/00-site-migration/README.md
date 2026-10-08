# 00-site-migration: Move the H200 site to the operator path

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 00-site-migration

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Adopt the existing weight disks as static PVs, install the Dynamo operator, GPU/Network Operator RDMA configuration and observability, stage weights for the production overlay, and start the in-cluster benchmark client.

**Hypothesis.** The production overlay schedules on the H200 site without hostNetwork or privileged mode, with RDMA through the shared device plugin, and serves the public endpoint through the Gateway.

## Layouts

Uses the production overlays in tracks/nvidia-dynamo/production (no per-experiment layouts).

## Dataset

```bash
# none
```

## Run

```bash
python tools/render_site.py --env platform/site.env tracks platform --out build/site
kubectl --context "$KUBE_CONTEXT" apply -k build/site/platform/sites/nebius-h200-2x8/storage/pv
helm upgrade --install dynamo-platform dynamo-platform-1.4.0.tgz -n dynamo-system --create-namespace \
  -f tracks/nvidia-dynamo/install/values-production.yaml
kubectl --context "$KUBE_CONTEXT" apply -k build/site/platform/operators
kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/observability
kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/production/gateway
kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/production/nemotron-3-nano-h200/namespace
kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano wait --for=condition=complete job/stage-weights --timeout=2h
kubectl --context "$KUBE_CONTEXT" apply -f build/site/tracks/nvidia-dynamo/studies/planned/common/benchmark-client.yaml
kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/production/nemotron-3-nano-h200/aggregated
kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano wait --for=condition=Ready dynamographdeployment/nemotron-3-nano --timeout=60m
```

## Success criteria

- Worker pods are Running with `rdma/rdma_shared_device_a` allocated and no hostNetwork.
- `curl https://nemotron-3-nano.<INFERENCE_DOMAIN>/v1/models` succeeds with a valid token and is rejected without one.
- `DynamoNoWorkersRegistered` is inactive; the dashboard shows TTFT/ITL for a smoke request.
- A 6-request disaggregated smoke test moves KV over NIXL (`sglang:kv_transfer_total_mb` > 0).

**Planning estimate:** 3-4 h including weight staging. See [READY.md](READY.md) before starting.
