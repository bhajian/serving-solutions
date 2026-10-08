# NVIDIA GPU and Network Operators

[Home](../../README.md) › [Platform](../README.md) › Operators

Pinned at **GPU Operator v26.7.1** and **Network Operator v26.7.0**; both are UNVALIDATED on
the H200 site (it currently runs a provider-managed GPU stack). Helm keys are tested against
the vendored chart values in `reference/upstream/nvidia-operators/`; the NicClusterPolicy is
validated against its v26.7.0 CRD.

| File | Purpose |
| --- | --- |
| [gpu-operator-values.yaml](gpu-operator-values.yaml) | Driver 595.91.07 with GPUDirect RDMA, container toolkit, device plugin, GPU Feature Discovery (`nvidia.com/gpu.product`), DCGM exporter with a ServiceMonitor |
| [network-operator-values.yaml](network-operator-values.yaml) | NFD on, SR-IOV off |
| [nic-cluster-policy.yaml](nic-cluster-policy.yaml) | RDMA shared device plugin publishing `rdma/rdma_shared_device_a` for Mellanox InfiniBand HCAs |

**Why no hostNetwork.** InfiniBand RDMA needs access to the HCA devices and locked memory,
not the host network namespace. The device plugin mounts `/dev/infiniband` into pods that
request `rdma/rdma_shared_device_a`, and `IPC_LOCK` allows memory registration. hostNetwork
remains necessary only for RoCE without a secondary network (Multus + SR-IOV), which this
site does not use.
