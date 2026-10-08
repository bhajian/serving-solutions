# Path 08 · Workload autoscaling

[Home](../../../../README.md) › [Tracks](../../../README.md) › [llm-d + Red Hat AI](../../README.md) › [Paths](../README.md) › 08 · Workload autoscaling

**Status: planned.** Upstream: [guides/workload-autoscaling](https://github.com/llm-d/llm-d/tree/release-0.10/guides/workload-autoscaling).

## What it adds

Scales model-server replicas on signals that lead latency (queue depth, in-flight requests, KV pressure) rather than on CPU or request counts.

## Choose it when

Diurnal or bursty traffic with an SLA goal and capacity that can be released when idle.

## Prerequisites

Path 01; an autoscaler (HPA/KEDA with the guide's metrics). Cold start must be short relative to the traffic ramp.

## Deploy

Start from the upstream guide with the RHAIIS image and pull secret from
[install](../../install/README.md), and reuse the per-site weight handling of
[path 01](../01-optimized-baseline/README.md). Constraint on this site: a DeepSeek V4 Pro replica takes about 35 minutes to load from a network disk, and each replica needs its own pre-filled RWO disk. Autoscaling large checkpoints needs shared fast storage or warm standby replicas.

## Test

A recorded ramp (low → peak → low); arms: fixed replicas against autoscaled. Metrics: SLO attainment during the ramp, GPU-hours used.
