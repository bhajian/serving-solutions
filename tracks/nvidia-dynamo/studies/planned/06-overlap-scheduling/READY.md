# 06-overlap-scheduling: ready-to-run checklist

## Cluster prerequisites

- [ ] `python tools/preflight.py tracks/nvidia-dynamo/studies/planned/06-overlap-scheduling --context "$KUBE_CONTEXT"` passes (GPU and RDMA
      capacity, CRDs, PVCs, image digests).
- [ ] [00-site-migration](../00-site-migration/) is complete: operator installed, weights staged
      in `model-weights` with `DEPLOYED_REVISION`, benchmark client running.
- [ ] Site manifests rendered: `python tools/render_site.py --env platform/site.env tracks platform --out build/site`.

## During the run

- [ ] Warm up after every layout change: the first disaggregated requests pay ~60 s of NIXL setup.
- [ ] Caches flushed before each measured run (`clear_cache.py` evidence appended to
      `study-records/cache-flush-evidence.jsonl`).
- [ ] One driver only: the sweep holds `build/experiments/06-overlap-scheduling/study-records/.driver.lock`.

## Results

- Raw runs: `/bench/results/06-overlap-scheduling/<run_id>/` in the client pod (PVC `benchmark-results`).
- Copy out with `kubectl cp`, then `python -m benchmarks.sweep table tracks/nvidia-dynamo/studies/06-overlap-scheduling` and
  `python tools/archive_results.pack` for the release archive. Mark the experiment's rows in
  ROADMAP.md validated only after the results are committed.
