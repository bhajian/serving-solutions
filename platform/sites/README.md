# Sites

[Home](../../README.md) › [Platform](../README.md) › Sites

A site is one physical cluster with its own hardware, network and storage. The track folders
hold what was deployed on each site; this folder holds what belongs to the cluster itself.

| Site | Hardware | Used by |
| --- | --- | --- |
| [nebius-h200-2x8](nebius-h200-2x8/README.md) | HGX H200, 8 × 141 GB per node, 8 × 400G InfiniBand per node; 2 nodes for the Dynamo studies, 4 from 2026-10-08 | Dynamo [lab profiles](../../tracks/nvidia-dynamo/sites/nebius-h200-2x8/README.md); llm-d [path 01](../../tracks/llm-d-redhat/paths/01-optimized-baseline/deepseek-v4-pro-h200/README.md) |
| hgx-b300-2x8 | 2 × HGX B300 (16 GPUs), InfiniBand; reference design, no recorded run | Dynamo [B300 reference tracks](../../tracks/nvidia-dynamo/sites/hgx-b300-2x8/README.md); llm-d [path 05 instance](../../tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/README.md) |
