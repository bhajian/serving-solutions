# Diagrams

[Home](../../README.md) › [Assets](../README.md) › Diagrams

Architecture diagrams for the README and blueprint. Each one is defined once as data in
[src/diagrams.py](src/diagrams.py) (boxes, groups, arrows and text on a pixel grid) and
rendered two ways by [tools/render_diagrams.py](../../tools/render_diagrams.py):

- `png/<name>.png`: 2x raster, at least 2400 px wide, for documents and slides
- `src/<name>.drawio`: the same geometry as editable draw.io XML

```bash
python tools/render_diagrams.py                 # all diagrams
python tools/render_diagrams.py serving-stack   # one diagram
```

Style: white background, neutral greys, one accent (NVIDIA green `#76B900`) for the
parts Dynamo provides or the data path being highlighted, one typeface (Inter, bundled in
[fonts/](fonts/) under the SIL Open Font License, so renders are identical everywhere), no
gradients or shadows. Text is sized to stay legible when a diagram is shown at README width
(about 60% of its native size): 14 px minimum on a 1400 px canvas.

The renderer refuses to finish if any text overflows its box or the canvas, crosses into a
box it does not belong to, or overlaps other text, so a layout edit cannot clip a label.
Diagrams quote measured numbers only from `tracks/nvidia-dynamo/studies/`; anything not yet run is labelled
UNVALIDATED.

| Diagram | Used in |
| --- | --- |
| [serving-stack](png/serving-stack.png) | README, blueprint index and 01 |
| [control-planes](png/control-planes.png) | README, blueprint 04 |
| [agg-vs-disagg](png/agg-vs-disagg.png) | blueprint 03, deploy tracks |
| [production-topology](png/production-topology.png) | README, blueprint 04 |
| [decision-flow](png/decision-flow.png) | blueprint 11 |
| [when-disaggregation-wins](png/when-disaggregation-wins.png) | blueprint 11 and 12 |
| [pd-parallelism](png/pd-parallelism.png) | blueprint 06 and 09 |
| [h200-site](png/h200-site.png) | README, blueprint 07, H200 site |
| [b300-reference](png/b300-reference.png) | blueprint 07, B300 tracks (UNVALIDATED) |
| [kv-cache-hierarchy](png/kv-cache-hierarchy.png) | blueprint 08 |
| [kv-transfer-datapath](png/kv-transfer-datapath.png) | blueprint 07 |
