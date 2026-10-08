# Legacy Docker Compose (single-node debugging only)

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Sites](../../README.md) › [hgx-b300-2x8](../README.md) › Legacy Compose

> **Not a production path.** These Compose files launch the same engines as the
> B300 reference tracks directly on hosts, without Kubernetes, the Dynamo operator,
> health management or network isolation. Use them to debug an engine or transfer
> setup on one or two machines. Production deployments use the
> [Dynamo operator path](../../../graphs/).

Each track folder holds `node-a.yaml` / `node-b.yaml` and a `deployment.json` run
record. Site values come from [`cluster.env.example`](cluster.env.example):

```bash
cp tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env.example tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env   # edit on both nodes
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env \
  -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml up -d
```
