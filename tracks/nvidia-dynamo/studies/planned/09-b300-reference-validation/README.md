# 09-b300-reference-validation: Validate the HGX B300 reference tracks end to end

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 09-b300-reference-validation

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Run tracks 01-04 (tracks/nvidia-dynamo/sites/hgx-b300-2x8) with Nemotron 3 Ultra 550B-A55B NVFP4 so the reference topology stops being unvalidated.

**Hypothesis.** The B300 manifests start and serve as tested offline; disaggregated tracks move KV over InfiniBand (port counters rise on the transfer path).

## Layouts

Uses the production overlays in tracks/nvidia-dynamo/production (no per-experiment layouts).

## Dataset

```bash
python tools/download_model.py   # on both nodes; pinned revision from configs/models.yaml
```

## Run

```bash
# For each track, in order 01 -> 02 -> 03 -> 04, follow its README:
#  1. deploy; 2. step 6 verification; 3. step 7 RDMA proof (IB counters before/after);
#  4. benchmarks.loadgen closed loop at concurrency 1/2/4/8 with the realistic dataset; 5. tear down.
python tools/render_site.py --env platform/site.env tracks platform --out build/site
```

## Success criteria

- Each track: all verification steps pass, RDMA proof recorded, results committed under tracks/nvidia-dynamo/studies/b300-*.
- README matrix row moved from ROADMAP.md only after results are committed.

**Planning estimate:** 4 tracks x ~2 h = ~8 h (one day). See [READY.md](READY.md) before starting.
