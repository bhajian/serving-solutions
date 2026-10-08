# Shared graph files

- `frontend_probe.py`: frontend readiness/liveness that requires discovered workers
  (frontend `/health` alone returns 200 with none).
- `sitecustomize.py`: opt-in GC freeze after warmup (`SERVING_GC_FREEZE_AFTER_S`).

Both are packaged as ConfigMaps by this Kustomize Component.
