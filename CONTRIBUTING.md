# Contributing

[Home](README.md) › Contributing

This repository is a reference architecture: readers must be able to understand **exactly** what runs. Contributions keep that property.

## Principles

- **Readable over automated.** Deployment files are hand-written and commented. Generators such as `tools/render.py` may help you draft, but the committed file is what readers study.
- **Every folder has a README.** A test enforces it.
- **Claims are sourced or measured.** Product capabilities cite pinned versions in [reference/sources.md](reference/sources.md). Performance claims come from [benchmarks/](benchmarks/) runs with their run records. Nothing is fabricated.
- **Unvalidated is labeled.** Anything not run on hardware says so.

## Where a contribution goes

| You are adding… | Put it in | Also update |
| --- | --- | --- |
| A decision rule, template or matrix row | [framework/](framework/README.md) | The blueprint chapter that explains it |
| Vendor-neutral explanation | [blueprint/](blueprint/README.md) | The framework row that cites it |
| A Dynamo deployment for a model on a site | `tracks/nvidia-dynamo/sites/<site>/<model>/` (lab) or the generators for `graphs/` and `production/` | [tracks/nvidia-dynamo/README.md](tracks/nvidia-dynamo/README.md) |
| An llm-d path instance (model × site) | `tracks/llm-d-redhat/paths/<nn-path>/<model>-<site>/` | The path guide's *Deploy* and *Status* sections |
| A new llm-d path guide | `tracks/llm-d-redhat/paths/<nn-path>/README.md` with the sections *What it adds · Choose it when · Prerequisites · Deploy · Test · Status* | [Track 2 README](tracks/llm-d-redhat/README.md) and the [pattern map](framework/2-decide/README.md#d4--pattern--implementation-map) |
| A study | `tracks/<track>/studies/<name>/`: README (question, protocol, status), drivers, data, report | The [evidence register](framework/4-validate/README.md#evidence-register) |
| Cluster prerequisites or a new site | [platform/](platform/README.md) | `platform/site.env.example` for any new placeholder |

Deployment files are hand-written and commented, except the folders marked as generated in
[tracks/nvidia-dynamo/README.md](tracks/nvidia-dynamo/README.md#generated-folders): edit their
generator and rerun it. Site-specific values are `<PLACEHOLDER>` tokens rendered from
`platform/site.env`; a test fails when a manifest uses one that the example file lacks.

## B300 reference tracks (Dynamo)

1. Create `tracks/nvidia-dynamo/sites/hgx-b300-2x8/NN-<topology>-<engine>/` and its Compose twin under `compose/`.
2. **Docker:** `node-a.yaml` and `node-b.yaml`. Site values come only from `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env`. Write engine flags out in full, with a comment above the `exec` line explaining each flag group.
3. **Kubernetes:** numbered manifests (`00-namespace`, `01-site-config`, `10-…`, `20-…`, `30-…`), a `kustomization.yaml` listing them in order, and a dedicated namespace.
4. **Run record:** a `deployment.json` with `technology`, `backend`, `topology`, `image`, `max_model_len` and `model` (id, revision, request defaults). Add new technology labels to `benchmarks/run.py`.
5. **Tests:** add the track to `tests/test_reference_manifests.py` so Compose and Kubernetes stay identical.

## Editing diagrams

Diagrams are PNG files (with editable draw.io sources) generated from [assets/diagrams/src/diagrams.py](assets/diagrams/src/diagrams.py) by [tools/render_diagrams.py](tools/render_diagrams.py). Edit the spec, never the PNG.

## Checks before a pull request

```bash
python -m pytest -q                 # offline: manifests, generator, metrics, notebook
python tools/validate.py            # upstream Kubernetes / Compose / InferencePool schemas
python tools/render_diagrams.py && git diff --stat assets/diagrams
```

## Writing style

Lead with the outcome. One idea per sentence. Tables for comparisons, numbered lists for steps. Name files and flags only where the reader must act on them.
