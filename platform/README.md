# Platform: the shared cluster layer

[Home](../README.md) › Platform

What every track needs from the cluster before a model server starts: GPU drivers and device
plugin, RDMA, storage for weights, and site-specific values. Nothing here is specific to Dynamo
or llm-d.

| Folder or file | Contents |
| --- | --- |
| [prerequisites/](prerequisites/README.md) | Host checks, RDMA test, model download |
| [operators/](operators/README.md) | NVIDIA GPU Operator and Network Operator values, NicClusterPolicy for the RDMA shared device plugin |
| [sites/](sites/README.md) | One folder per physical cluster: hardware description and shared storage objects |
| [site.env.example](site.env.example) | Every site-specific value (kube context, node names, addresses, disk handles, domains) as placeholders |

## Site values

Checked-in manifests carry `<PLACEHOLDER>` tokens instead of real hostnames and addresses.
Copy [site.env.example](site.env.example) to `platform/site.env` (git-ignored), fill it in,
and render. Rendered files mirror their repository path under `build/site/`:

```bash
python tools/render_site.py --env platform/site.env tracks platform --out build/site
```
