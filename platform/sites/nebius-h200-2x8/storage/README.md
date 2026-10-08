# Shared model storage (H200 site)

[Home](../../../../README.md) › [Platform](../../../README.md) › [Sites](../../README.md) › [nebius-h200-2x8](../README.md) › Storage

The site has two 1500Gi ReadWriteOnce network SSD disks, one per GPU node. Each holds
both models' weights in separate directories. A ReadWriteOnce volume binds to one
PersistentVolumeClaim at a time, so the two model profiles share the disks through
**static PersistentVolumes** rather than one profile reusing the other's namespace.

| Folder | Contents |
| --- | --- |
| [pv/](pv/) | Cluster-scoped PVs `h200-model-disk-a` / `-b` with `Retain` reclaim policy. `volumeHandle` comes from `MODEL_DISK_A_HANDLE` / `MODEL_DISK_B_HANDLE` in `platform/site.env`. |
| [claims-nemotron-3-nano/](claims-nemotron-3-nano/) | PVCs `model-0` / `model-1` in `nemotron-3-nano`, pinned with `volumeName`. |
| [claims-deepseek-v4-pro/](claims-deepseek-v4-pro/) | The same claims in `deepseek-v4-pro`. |

## Switch the disks between model profiles

> **UNVALIDATED — scheduled.** The measured runs used dynamically provisioned PVCs in
> `deepseek-v4-pro`. This static-PV migration has not been run on the cluster; it is
> step 1 of [tracks/nvidia-dynamo/studies/planned/00-site-migration](../../../../tracks/nvidia-dynamo/studies/planned/00-site-migration/).

```bash
# Once: adopt the existing disks as static PVs. Read the handles first:
kubectl --context "$KUBE_CONTEXT" get pv -o custom-columns=NAME:.metadata.name,HANDLE:.spec.csi.volumeHandle,CLAIM:.spec.claimRef.name
python tools/render_site.py --env platform/site.env platform/sites/nebius-h200-2x8/storage --out build/site
# Set Retain on the dynamically provisioned PVs before deleting their claims, so the data survives.
kubectl --context "$KUBE_CONTEXT" patch pv <old-pv> -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'

# To move the disks from one profile to the other: stop the old profile's pods,
# delete its claims, clear the PVs' claimRef, then apply the other profile's claims.
kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro delete pvc model-0 model-1
for pv in h200-model-disk-a h200-model-disk-b; do
  kubectl --context "$KUBE_CONTEXT" patch pv $pv --type json -p '[{"op":"remove","path":"/spec/claimRef"}]'
done
kubectl --context "$KUBE_CONTEXT" apply -k build/site/platform/sites/nebius-h200-2x8/storage/claims-nemotron-3-nano
```

Only one profile can mount the disks at a time. For concurrent profiles, use a
ReadWriteMany filesystem or one disk set per profile; the production overlay
pre-stages weights instead (see [tracks/nvidia-dynamo/production](../../../../tracks/nvidia-dynamo/production/)).
