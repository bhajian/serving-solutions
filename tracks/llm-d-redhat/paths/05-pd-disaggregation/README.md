# Path 05 · P/D disaggregation

[Home](../../../../README.md) › [Tracks](../../../README.md) › [llm-d + Red Hat AI](../../README.md) › [Paths](../README.md) › 05 · P/D disaggregation

**Status: reference manifests**, UNVALIDATED: [hgx-b300-qwen3-coder-480b/](hgx-b300-qwen3-coder-480b/README.md)
(Qwen3-Coder-480B FP8 on 2 × HGX B300, vLLM 0.30.0 and SGLang 0.5.20 variants, stock images).
Upstream: [guides/pd-disaggregation](https://github.com/llm-d/llm-d/tree/release-0.10/guides/pd-disaggregation).

## What it adds

Separate prefill and decode pools. The router picks a decode pod; a routing sidecar on that
pod sends the prompt to a prefill pod first, then decodes with the transferred KV (NIXL over
UCX/RDMA). vLLM runs prefill as `kv_producer` and decode as `kv_consumer`.

## Choose it when

All six P/D preconditions hold ([framework D1](../../../../framework/2-decide/README.md#d1--serving-pattern)):
both phases substantial (0.15 ≲ *R* ≲ 7), tight p99 ITL, a fleet large enough to tune the P:D
ratio, per-phase parallelism, working prefix-aware routing, and RDMA. The Dynamo studies show
P/D losing at a fixed 1P:1D on two nodes while removing decode stalls
([evidence](../../../../framework/4-validate/README.md#evidence-register)).

## Prerequisites

[Install](../../install/README.md), GPUDirect RDMA between nodes ([platform](../../../../platform/prerequisites/README.md)),
Kubernetes 1.33+ for native sidecars.

## Deploy

The reference instance uses stock upstream images. To move it to RHAIIS: replace the vLLM
image with the RHAIIS image and digest, add the `rh-registry` pull secret, and confirm the
image's NIXL/UCX build supports the fabric.

## Test

SLA goal: open-loop goodput at p99 TTFT and ITL across P:D ratios, against path 01 on the same
GPUs (study type in [4 · Validate](../../../../framework/4-validate/README.md#validation-ladder)).
