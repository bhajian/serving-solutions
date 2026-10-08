# Path 03 · Predicted-latency routing

[Home](../../../../README.md) › [Tracks](../../../README.md) › [llm-d + Red Hat AI](../../README.md) › [Paths](../README.md) › 03 · Predicted-latency routing

**Status: planned.** Upstream: [guides/predicted-latency-routing](https://github.com/llm-d/llm-d/tree/release-0.10/guides/predicted-latency-routing).

## What it adds

Routes on predicted TTFT and TPOT per pod from a model trained live on observed requests (XGBoost), instead of a fixed combination of queue depth, KV utilization and prefix scores.

## Choose it when

Heterogeneous request sizes and an SLA goal: the right pod depends on how long its queue will take, which fixed scorers estimate poorly. Framework goal *SLA-optimized*.

## Prerequisites

Path 01; the predictor service and its training sidecars from the upstream guide.

## Deploy

Start from the upstream guide with the RHAIIS image and pull secret from
[install](../../install/README.md), and reuse the per-site weight handling of
[path 01](../01-optimized-baseline/README.md). Pending: confirm the predictor's resource needs and that it trains on RHAIIS vLLM metrics unchanged.

## Test

Open-loop load with mixed ISL (lognormal) at a p99 TTFT/ITL SLO; arms: path 01 against predicted-latency. Metric: goodput and SLO attainment across load.
