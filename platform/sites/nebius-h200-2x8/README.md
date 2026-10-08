# Nebius H200 cluster

[Home](../../../README.md) › [Platform](../../README.md) › [Sites](../README.md) › nebius-h200-2x8

| Item | Value |
| --- | --- |
| Kubernetes | Nebius managed Kubernetes, v1.36; Cilium CNI |
| GPU nodes | `gpu-h200-sxm`, preset `8gpu-128vcpu-1600gb`: 8 × H200 141 GB, 128 vCPU, 1.6 TB RAM; `cuda13.0` driver preset |
| Node count | 2 during the Dynamo studies (September 2026); 4 from 2026-10-08 |
| Fabric | 8 × 400G InfiniBand per node (`mlx5_4`–`mlx5_11`), GPUDirect RDMA |
| Storage | `compute-csi-default-sc`: network SSD, ReadWriteOnce, no snapshot class, no ReadWriteMany class; about 400–450 MB/s read per 1500Gi disk |

Weights therefore live on one RWO disk per model-server replica. Shared static PersistentVolumes
for the Dynamo profiles: [storage/](storage/README.md). Per-replica claims for llm-d path 01 are
created with that path's manifests.
