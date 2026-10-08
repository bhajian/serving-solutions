# Path 07 · Flow control

[Home](../../../../README.md) › [Tracks](../../../README.md) › [llm-d + Red Hat AI](../../README.md) › [Paths](../README.md) › 07 · Flow control

**Status: planned.** Upstream: [guides/flow-control](https://github.com/llm-d/llm-d/tree/release-0.10/guides/flow-control).

## What it adds

Queues requests in the router by priority and fairness when the pool is saturated, instead of admitting everything and letting latency collapse; detects saturation from pod metrics.

## Choose it when

Multi-tenant serving or bursty traffic with an SLA goal; protects interactive tenants from batch floods.

## Prerequisites

Path 01; the router's `flowControl` feature and its saturation detector configured with real thresholds (path 01 neutralizes them for its routing study).

## Deploy

Start from the upstream guide with the RHAIIS image and pull secret from
[install](../../install/README.md), and reuse the per-site weight handling of
[path 01](../01-optimized-baseline/README.md). Pending: thresholds for long-context models, where KV usage above 0.8 is normal rather than a saturation signal.

## Test

Two tenants, one bursty batch tenant and one interactive tenant with a p99 TTFT SLO; arms: without and with flow control. Metric: the interactive tenant's SLO attainment during bursts.
