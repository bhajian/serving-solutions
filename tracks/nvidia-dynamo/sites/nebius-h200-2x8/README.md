# Nebius HGX H200 2 × 8 — validated site

[Home](../../../../README.md) › [Tracks](../../../README.md) › [NVIDIA Dynamo](../../README.md) › [Sites](../README.md) › nebius-h200-2x8

Two HGX H200 nodes (8 × H200 141 GB each, 16 GPUs total) in a managed Kubernetes
cluster, with eight InfiniBand interfaces per node for NIXL/UCX transfer and two
1500Gi network SSD PVCs for weights. All measured results in this repository come
from this site.

| Model profile | Studies | Results |
| --- | --- | --- |
| [deepseek-v4-pro](deepseek-v4-pro/) | 256K input, aggregated vs 1P+1D (TP8) | [tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison](../../studies/deepseek-v4-pro-256k-comparison/) |
| [nemotron-3-nano](nemotron-3-nano/) | 128K input / 256 output (TP8); 8K input / 128K output (TP4) | [128K](../../studies/nemotron-3-nano-128k-comparison/), [8K/128K](../../studies/nemotron-3-nano-8k-128k-comparison/) |

The manifests used for those measurements are kept unchanged in each profile's
`lab/` folder (hostNetwork workers, single etcd, hand-written Deployments). The
operator-managed production path for this site is described in
[tracks/nvidia-dynamo/README.md](../../README.md).
