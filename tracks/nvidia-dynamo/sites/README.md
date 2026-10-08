# Sites

[Home](../../../README.md) › [Tracks](../../README.md) › [NVIDIA Dynamo](../README.md) › Sites

A site is one physical cluster with its own hardware, network and storage. Each
site folder holds the model profiles that have been deployed there.

| Site | Hardware | Status |
| --- | --- | --- |
| [nebius-h200-2x8](nebius-h200-2x8/) | 2 × HGX H200 (16 GPUs), 8 × 400G InfiniBand per node | **Validated**: DeepSeek V4 Pro (256K), Nemotron 3 Nano (128K in; 8K in / 128K out) |
| [hgx-b300-2x8](hgx-b300-2x8/) | 2 × HGX B300 (16 GPUs), InfiniBand | **UNVALIDATED reference topology**: manifests are structurally tested but have not been run end to end |

Site-specific values (node names, addresses, kube context) are never committed.
Copy [`../site.env.example`](../../../platform/site.env.example) to `platform/site.env` and render
manifests with `tools/render_site.py`.
