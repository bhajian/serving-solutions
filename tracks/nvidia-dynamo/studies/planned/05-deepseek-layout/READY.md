# 05-deepseek-layout: ready-to-run checklist

## Cluster prerequisites

- [ ] `python tools/preflight.py tracks/nvidia-dynamo/studies/planned/05-deepseek-layout --context "$KUBE_CONTEXT"` passes (GPU and RDMA
      capacity, CRDs, PVCs, image digests).
- [ ] [00-site-migration](../00-site-migration/) is complete: operator installed, weights staged
      in `model-weights` with `DEPLOYED_REVISION`, benchmark client running.
- [ ] Site manifests rendered: `python tools/render_site.py --env platform/site.env tracks platform --out build/site`.

## During the run

- [ ] Warm up after every layout change: the first disaggregated requests pay ~60 s of NIXL setup.
- [ ] Caches flushed before each measured run (`clear_cache.py` evidence appended to
      `study-records/cache-flush-evidence.jsonl`).
- [ ] One driver only: the sweep holds `build/experiments/05-deepseek-layout/study-records/.driver.lock`.

## Results

- Raw runs: `/bench/results/05-deepseek-layout/<run_id>/` in the client pod (PVC `benchmark-results`).
- Copy out with `kubectl cp`, then `python -m benchmarks.sweep table tracks/nvidia-dynamo/studies/05-deepseek-layout` and
  `python tools/archive_results.pack` for the release archive. Mark the experiment's rows in
  ROADMAP.md validated only after the results are committed.
