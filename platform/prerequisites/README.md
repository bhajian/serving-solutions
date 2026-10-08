# 00 · Prerequisites

[Home](../../README.md) › [Platform](../README.md) › 00 · Prerequisites

Complete this page once. Every deployment track assumes it is done.

![Reference deployment topology](../../assets/diagrams/png/b300-reference.png)

**Contents**

1. [Reference hardware](#1-reference-hardware)
2. [Software](#2-software)
3. [Network and ports](#3-network-and-ports)
4. [Check each GPU server](#4-check-each-gpu-server)
5. [Test the RDMA data path](#5-test-the-rdma-data-path)
6. [Download the model on both nodes](#6-download-the-model-on-both-nodes)
7. [Platform setup: Docker or Kubernetes](#7-platform-setup-docker-or-kubernetes)

Run commands from the repository root unless a step says otherwise. A block labeled **Both nodes** runs once on each GPU server.

---

## 1. Reference hardware

| | Node A | Node B |
|---|---|---|
| Role (aggregated) | frontend + etcd + replica 1 | replica 2 |
| Role (disaggregated) | frontend + etcd + **prefill** | **decode** |
| GPUs | 8 × NVIDIA B300 (NVLink) | 8 × NVIDIA B300 (NVLink) |
| Private IP (example) | <B300_NODE_A_IP> on `eth0` | <B300_NODE_B_IP> on `eth0` |
| InfiniBand | `mlx5_4` … `mlx5_11`, port 1, 800 Gb/s | same |
| RAM / free disk observed | 2.6 TiB / 973 GiB | 2.6 TiB / 973 GiB |
| GPU driver observed | 580.173.02 | 580.173.02 |

**Single-node lab:** the aggregated track ([01](../../tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/)) runs on Node A alone. The disaggregated tracks need both nodes.

**Other hardware:** any 8-GPU NVLink server with enough memory for the model at TP8 works. Adjust `IB_DEVICES` and the interface name to your system. Disaggregation across nodes needs RDMA (InfiniBand or RoCE) with GPUDirect RDMA.

---

## 2. Software

| Needed on | Docker path | Kubernetes path |
|---|---|---|
| GPU servers | Linux, NVIDIA driver 580+, NVIDIA Container Toolkit, Docker Engine, **Docker Compose 2.30+**, MLNX_OFED/DOCA-OFED InfiniBand drivers, `nvidia-peermem` (GPUDirect RDMA) | Same drivers, installed directly or by the **NVIDIA GPU Operator** and **Network Operator** |
| Cluster | n/a | Kubernetes 1.29+ (1.33+ for [04 · llm-d](../../tracks/llm-d-redhat/paths/05-pd-disaggregation/hgx-b300-qwen3-coder-480b/)), a CNI, GPUs advertised as `nvidia.com/gpu` |
| Your workstation | SSH | `kubectl` (plus `helm` for llm-d) |
| Benchmark client | Python 3.11+ | Python 3.11+ |

Benchmark client setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Network and ports

Allow trusted traffic between the two private IPs. Dynamo and UCX also use **dynamically allocated ports**, so opening only the ports below is not sufficient. Keep all of them off public interfaces.

| Port | Where | Used by | Tracks |
|---|---|---|---|
| 8000 | Node A | Dynamo frontend (OpenAI API) | all |
| 2379 | Node A | etcd client (Docker path) | all |
| 8081 | each worker node | worker `/health` and `/metrics` | all |
| 5600 | each worker node | vLLM NIXL side channel | 04 |
| 8998 | Node A | SGLang disaggregation bootstrap | 05 |
| 30000 | each worker node | SGLang internal HTTP port | 03 SGLang, 05 |
| 18515 | both | `ib_write_bw` test handshake | this page |
| RDMA | IB fabric | KV-cache transfer (NIXL/UCX) | 04, 05 |

---

## 4. Check each GPU server

**Both nodes:**

```bash
hostname
ip -4 -br addr show dev eth0          # expect the node's private IP
nvidia-smi                            # expect 8 GPUs, driver 580+
nvidia-smi topo -m                    # GPU-to-HCA affinity (look for PIX/PXB per GPU)
docker version                        # Docker path only
ls /dev/infiniband                    # RDMA devices present
ibv_devinfo -l                        # HCA names for IB_DEVICES
lsmod | grep -E 'nvidia_peermem|nv_peer_mem' || echo "GPUDirect RDMA module not loaded"
ulimit -l                             # should be "unlimited" for RDMA
df -h /data && free -h
```

`nvidia_peermem` enables GPUDirect RDMA on hosts that do not use DMA-BUF. Without GPUDirect, UCX can fall back to staging through host memory. That still works but is slower, and it defeats the purpose of [the KV data path](../../blueprint/07-hardware-network-storage.md#the-kv-data-path-gpudirect-rdma-over-rails).

The repository's preflight script bundles the host checks once the model is downloaded:

```bash
bash tools/preflight.sh /data/nemotron-ultra/model eth0
```

---

## 5. Test the RDMA data path

*Required for disaggregated tracks. Optional for aggregated.*

HTTP connectivity says nothing about RDMA, so test the fabric directly, one rail at a time.

**Both nodes:** install perftest if missing.

```bash
sudo apt-get install -y perftest
```

**Node A first** (it waits for the client):

```bash
sudo ib_write_bw -d mlx5_4 -i 1 -p 18515 --report_gbits -D 10
```

**Node B second:**

```bash
sudo ib_write_bw -d mlx5_4 -i 1 -p 18515 --report_gbits -D 10 <B300_NODE_A_IP>
```

Repeat for `mlx5_5` … `mlx5_11`. Expect close to line rate on each rail. The private IP only carries the handshake; the payload uses the InfiniBand device.

**GPU memory test (recommended).** If perftest was built with CUDA support, add `--use_cuda=<gpu index>` on both sides. This exercises GPUDirect RDMA from GPU memory, which is what NIXL uses.

**Interpreting results:** `ibdev2netdev` may show IPoIB netdevs as *Down*. That does not block native verbs traffic, and you should not assign IPs just to change it. If a test fails, check private-IP routing and TCP 18515 first for connection errors, then fabric partitions and RDMA configuration for verbs errors. Do not disable firewalls globally.

---

## 6. Download the model on both nodes

Every worker loads the **complete** checkpoint and shards it over its 8 GPUs, so both nodes need a full copy of the **same revision**. The reference model is **NVIDIA Nemotron 3 Ultra 550B-A55B NVFP4**, about 352 GB, pinned to revision `252a02f921642313abde19b29a723a16602fe25e`.

**Both nodes**, using the benchmark virtualenv:

```bash
# Only if the repository requires authentication. The token is never written to disk by these tools.
read -rsp 'Hugging Face token: ' HF_TOKEN; echo; export HF_TOKEN

sudo install -d -o "$(id -u)" -g "$(id -g)" /data/nemotron-ultra/model /data/nemotron-ultra/runtime
python tools/download_model.py --model nemotron-ultra --check-only    # capacity check, no download
python tools/download_model.py --model nemotron-ultra
cat /data/nemotron-ultra/model/DEPLOYED_REVISION                      # must match on both nodes
```

The downloader resolves the pinned revision and checks free disk space first. It writes `DEPLOYED_REVISION`, which every worker checks at startup, and refuses to mix revisions in one directory.

<details>
<summary>Alternative: download with the runtime container (no Python setup on the host)</summary>

```bash
IMAGE=nvcr.io/nvidia/ai-dynamo/vllm-runtime:1.4.0@sha256:8401411dc8e968eff9310462102491509e3f93d3ce03d6febc8d5566f067a7b1
docker run --rm -i --user 0 -e HF_TOKEN -e HF_HOME=/tmp/hf \
  -v /data/nemotron-ultra/model:/model --entrypoint python3 "$IMAGE" - <<'PY'
from pathlib import Path
from huggingface_hub import snapshot_download
rev = '252a02f921642313abde19b29a723a16602fe25e'
snapshot_download(repo_id='nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4', revision=rev,
                  local_dir='/model', max_workers=4)
Path('/model/DEPLOYED_REVISION').write_text(rev + '\n')
PY
```

</details>

Other models are covered in [reference/models.md](../../reference/models.md).

---

## 7. Platform setup: Docker or Kubernetes

### Docker path

**Both nodes:** copy the repository and create the site settings file.

```bash
git clone <this repository> && cd <repository>
cp tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env.example tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env
vi tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env        # NODE_A_IP, NODE_B_IP, IP_IFACE, IB_DEVICES, MODEL_DIR, RUNTIME_DIR
```

`tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env` is identical on both nodes. Each Compose file reads it with `--env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env`.

### Kubernetes path

**Your workstation:** confirm GPUs are schedulable, then label the two GPU nodes. The labels are the only way the manifests choose nodes, so no YAML edits are needed for placement.

```bash
kubectl get nodes -o wide                                        # INTERNAL-IP should be the private IP
kubectl describe node <node-a> | grep -A3 'nvidia.com/gpu'       # expect 8

kubectl label node <node-a> llm-serving/node=node-a
kubectl label node <node-b> llm-serving/node=node-b
kubectl get nodes -L llm-serving/node
```

Workers use host networking and read their IP from `status.hostIP`, the node's **InternalIP**. If `kubectl get nodes -o wide` shows a different address than the private `eth0` IP, fix the kubelet `--node-ip` first.

For disaggregated tracks, confirm pods can use RDMA. The reference manifests run workers **privileged** with `/dev/infiniband` mounted, which is the simplest lab setup. If you run the NVIDIA Network Operator with an RDMA device plugin, see the comment in each worker manifest.

---

**Next:** [01 · Aggregated serving](../../tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/) (baseline) · or back to the [blueprint](../../blueprint/)
