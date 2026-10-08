# Nemotron 3 Ultra with Dynamo + vLLM

[Home](../../../../README.md) › [Tracks](../../../README.md) › [NVIDIA Dynamo](../../README.md) › [Sites](../README.md) › [hgx-b300-2x8](README.md) › Manual Docker walkthrough

> This is the original hand-run deployment that the repository grew from. It is kept unchanged as a reference. It contains the host-specific SSH details and fixes (such as the `DYN_TCP_RESPONSE_STREAM_HOST` issue) that the reference deployment files are based on. To deploy, use the Compose files in [tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm](compose/02-dynamo-disagg-vllm/), which run the same containers.

**Run location:** Fresh installation / 29 September 2026

Install Nemotron 3 Ultra on two B300 servers using Docker, with vLLM workers behind a Dynamo frontend. Node A performs prefill; Node B performs decode. Each worker uses eight GPUs. The initial configuration uses a 32K context limit with MTP disabled.

| Setting | Node A / prefill | Node B / decode |
| --- | --- | --- |
| Private IP | <B300_NODE_A_IP> | <B300_NODE_B_IP> |
| SSH from your computer | <ssh-user>@<B300_NODE_A_PUBLIC_IP> | <ssh-user>@<B300_NODE_B_PUBLIC_IP> |
| GPU assignment | 8 x B300 / TP8 | 8 x B300 / TP8 |
| Dynamo frontend + etcd | Run here only | Connect to Node A |
| IP interface | eth0 | eth0 |
| InfiniBand ports | mlx5_4 through mlx5_11, port 1 | mlx5_4 through mlx5_11, port 1 |
| Available RAM / disk observed | 2.6 TiB / 973 GiB | 2.6 TiB / 973 GiB |

### What runs where

```text
Client -> Node A:8000 (Dynamo frontend)
             |-> Node A: vLLM prefill / TP8
             |-> Node B: vLLM decode  / TP8

Prefill -> decode: attention KV + Mamba state via NIXL/UCX/IB
Both nodes -> Node A:2379: etcd service discovery
```

Both workers load the **complete NVFP4 checkpoint**, sharded across their local GPUs. The checkpoint is about 352 GB per node. No cross-node Ray cluster is needed. [1]

**Scope:** this is a fresh application deployment on your existing Linux servers. It assumes no etcd, Dynamo frontend or Ultra worker containers are running. Follow the steps in order; each command block identifies where it runs. This Markdown includes the response-stream correction confirmed during setup; use this revision instead of the earlier guide.

**Validation:** this Docker guide adapts NVIDIA's model-specific recipe to B300 TP8/TP8. Both workers completed initialization and registered in the supplied logs. You reported that removing the frontend response-stream host override resolved the frontend issue. End-to-end inference and RDMA performance still require their own checks. [2,3]


## Before you begin

**Run location:** Your computer, then both servers

Open two terminal windows on your computer. Connect each window to one server and keep them open throughout the installation.

### Terminal A: connect to the prefill server

```bash
ssh <ssh-user>@<B300_NODE_A_PUBLIC_IP>
```

### Terminal B: connect to the decode server

```bash
ssh <ssh-user>@<B300_NODE_B_PUBLIC_IP>
```

Run the following commands **inside both SSH sessions**, not on your computer:

```bash
bash
hostname
ip -4 -br addr show dev eth0
nvidia-smi
docker version
df -h /
free -h
```

Terminal A must show private IP **<B300_NODE_A_IP>**; Terminal B must show **<B300_NODE_B_IP>**. Each server should expose eight available B300 GPUs. Docker Engine, the NVIDIA Container Toolkit and the InfiniBand host drivers must be installed before continuing.

Both servers have already reported driver 580.173.02, approximately 2.6 TiB available RAM and 973 GiB free disk. Verify the current capacity before downloading the checkpoint. The pinned runtime requires a compatible 580.xx+ driver. [4]

The commands assume the user **ben** can run Docker. If docker version reports a daemon permission error, have the administrator grant the intended Docker access before continuing. If the NVIDIA Container Toolkit is missing, follow the linked installation guide in the references. [10]

### Network access needed

Permit trusted communication between the two private IPs. Node B must reach Node A on TCP 2379 for etcd and TCP 8000 for API tests. The RDMA check uses TCP 18515 for its handshake. Dynamo and UCX also use dynamically allocated ports, so opening only those three ports is insufficient. Keep these services on the private network.

Run the blocks labeled **Both nodes** once in each terminal. Run **Node A only** blocks only in Terminal A. Parenthesized blocks run in a subshell and stop at the first failed command; if a block fails, resolve the error before continuing.


## 1. Create directories and settings

**Run location:** Both nodes / run in bash

Run this block once in each SSH terminal. It creates the deployment directories, saves the fixed node addresses and detects whether the local server is the prefill or decode node.

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" \
  /data/nemotron-ultra \
  /data/nemotron-ultra/model \
  /data/nemotron-ultra/runtime \
  /data/nemotron-ultra/scripts

cat > /data/nemotron-ultra/settings.sh <<'SH'
export DATA=/data/nemotron-ultra
export NODE_A_IP=<B300_NODE_A_IP>
export NODE_B_IP=<B300_NODE_B_IP>
export IP_IFACE=eth0
export MODEL_ID=nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4
export MODEL_REVISION=252a02f921642313abde19b29a723a16602fe25e
IMAGE_DIGEST=8401411dc8e968eff9310462102491509e3f93d3ce03d6febc8d5566f067a7b1
export IMAGE="nvcr.io/nvidia/ai-dynamo/vllm-runtime:1.4.0@sha256:$IMAGE_DIGEST"
export IB_DEVICES=mlx5_4:1,mlx5_5:1,mlx5_6:1,mlx5_7:1,mlx5_8:1,mlx5_9:1,mlx5_10:1,mlx5_11:1

unset LOCAL_IP ROLE
LOCAL_IP=$(ip -4 -o addr show dev eth0 | awk '{print $4}' | cut -d/ -f1)
case "$LOCAL_IP" in
  <B300_NODE_A_IP>) ROLE=prefill ;;
  <B300_NODE_B_IP>) ROLE=decode ;;
  *) echo "STOP: unexpected eth0 IP: $LOCAL_IP" >&2; return 1 ;;
esac
export LOCAL_IP ROLE

require_role() {
  if [ "$ROLE" != "$1" ]; then
    echo "STOP: requires role $1; this node is $ROLE" >&2
    return 1
  fi
}
printf 'Node=%s Role=%s Etcd=%s:2379\n' "$LOCAL_IP" "$ROLE" "$NODE_A_IP"
SH

source /data/nemotron-ultra/settings.sh
```

**Every new SSH terminal:** reload settings before continuing. The later command blocks also do this explicitly.

```bash
source /data/nemotron-ultra/settings.sh
```

Expected: Node A prints **<B300_NODE_A_IP> / prefill**; Node B prints **<B300_NODE_B_IP> / decode**. Both print etcd at **<B300_NODE_A_IP>:2379**. Stop if the node or role differs.


## 2. Check Docker and RDMA

**Run location:** Both nodes / before starting workers

Pull the runtime image pinned by the NVIDIA recipe, then verify that Docker can see all eight GPUs. Use the same image digest on both nodes. Keep the bundled vLLM and NIXL versions unchanged. [3,4]

```bash
source /data/nemotron-ultra/settings.sh
docker pull "$IMAGE"
docker run --rm --gpus all --entrypoint nvidia-smi "$IMAGE"
df -h "$DATA"
docker system df
```

### Test one InfiniBand port pair

Install perftest on both nodes if missing. Confirm that their private IPs can communicate and that TCP 18515 is allowed between them for this test.

```bash
sudo apt-get install -y perftest
```

**Node A first** (waits for the client):

```bash
sudo ib_write_bw -d mlx5_4 -i 1 -p 18515 --report_gbits -D 10
```

**Node B second:**

```bash
sudo ib_write_bw -d mlx5_4 -i 1 -p 18515 --report_gbits -D 10 <B300_NODE_A_IP>
```

The private IP carries the setup handshake; the payload uses the selected InfiniBand device. Use matching options on both sides. Repeat with mlx5_5 through mlx5_11, one pair at a time. These tests validate host-memory RDMA, not GPU-direct RDMA or NIXL. [5]

### Interpret the checks correctly

The supplied mlx5_4 through mlx5_11 ports report Active/LinkUp, 800 Gb/s and MTU 4096. The IP-over-InfiniBand netdevs showing Down do not by themselves prevent native verbs transfers. Do not assign IP addresses or change those interfaces just to make ibdev2netdev show Up.

Use mlx5_4 through mlx5_11 for the transfer tests. A link inventory or subnet-management query is not a substitute for an actual transfer test.

**If the RDMA test fails:** stop before launching the workers. Preserve output from both sides. Check private-IP routing/TCP 18515 first for connection failures, then fabric partition/access and RDMA configuration for verbs failures. Do not disable firewalls globally.


## 3. Start etcd on Node A

**Run location:** Node A only / <B300_NODE_A_IP>

Start one etcd container on Node A for service discovery. Its client listener binds to **0.0.0.0:2379** (all IPv4 interfaces). It advertises **http://<B300_NODE_A_IP>:2379**, which both workers and the frontend use to connect. The command checks the local node role before starting the service.

```bash
(
set -e
source /data/nemotron-ultra/settings.sh
require_role prefill

docker run -d \
  --name dynamo-etcd \
  --restart unless-stopped \
  --network host \
  -v nemotron-ultra-etcd-data:/etcd-data \
  quay.io/coreos/etcd:v3.5.21 \
  /usr/local/bin/etcd \
  --name default \
  --data-dir /etcd-data \
  --listen-client-urls http://0.0.0.0:2379 \
  --advertise-client-urls http://<B300_NODE_A_IP>:2379 \
  --listen-peer-urls http://127.0.0.1:2380 \
  --initial-advertise-peer-urls http://127.0.0.1:2380 \
  --initial-cluster default=http://127.0.0.1:2380
)
```

### Confirm that etcd is running

**Node A:** check the container and its startup logs.

```bash
docker ps --filter name=dynamo-etcd
docker logs --tail 30 dynamo-etcd
```

**Both nodes:** after a few seconds, check Node A. Expect a JSON response containing **"health":"true"**. Do not proceed until both checks pass.

```bash
curl -fsS --connect-timeout 5 http://<B300_NODE_A_IP>:2379/health
```

This single-node etcd setup is for initial deployment on a trusted private network. Restrict 2379 to the required nodes; it is not configured with authentication, TLS or high availability.

**Checkpoint:** continue only after the health request succeeds from both terminals. Node B connects to Node A's etcd service; it does not run its own etcd container.


## 4. Download the model

**Run location:** Both nodes / same pinned revision

Download one complete checkpoint to /data/nemotron-ultra/model on each node. Both use the model revision saved in settings.sh. The runtime image does not include model weights. [1,6]

If authentication is needed, enter the token in each host shell using the following hidden prompt. Do not put the token in settings.sh or common.env.

```bash
read -rsp 'Hugging Face token: ' HF_TOKEN; echo
export HF_TOKEN
```

```bash
(
set -e
source /data/nemotron-ultra/settings.sh
docker run --rm -i \
  --user 0 \
  -e HF_TOKEN -e MODEL_ID -e MODEL_REVISION \
  -e HF_HOME=/runtime/hf \
  -e HF_XET_CHUNK_CACHE_SIZE_BYTES=0 \
  -v "$DATA/model:/model" \
  -v "$DATA/runtime/download:/runtime" \
  --entrypoint python3 "$IMAGE" - <<'PY'
import os
from pathlib import Path
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id=os.environ['MODEL_ID'],
    revision=os.environ['MODEL_REVISION'],
    local_dir='/model',
    max_workers=4,
)
required = [
    'config.json', 'tokenizer.json', 'tokenizer_config.json',
    'generation_config.json', 'ultra_v3_reasoning_parser.py',
]
missing = [x for x in required if not Path('/model', x).is_file()]
if missing:
    raise RuntimeError(f'Missing model files: {missing}')
Path('/model/DEPLOYED_REVISION').write_text(
    os.environ['MODEL_REVISION'] + '\n'
)
print('Model download and file checks complete.')
PY
)
```

Confirm the revision file matches on both nodes and monitor free disk:

```bash
cat /data/nemotron-ultra/model/DEPLOYED_REVISION
du -sh /data/nemotron-ultra/model
df -h /data/nemotron-ultra
```

The NVFP4 repository is approximately 352 GB. Download directly into the model directory; do not add a second cached weight copy or download BF16 to quantize locally. The two supplied hosts each showed 973 GiB free before installation.


## 5. Create the runtime environment

**Run location:** Both nodes / create common.env

Run this on both nodes. Local addresses are detected by settings.sh. Both use Node A for discovery and the eight intended InfiniBand ports for UCX. These settings use TCP requests and ZMQ events; NATS is not needed. [7,8]

```bash
(
set -e
source /data/nemotron-ultra/settings.sh
cat > "$DATA/common.env" <<EOF
DYN_NAMESPACE=nemotron-ultra
DYN_DISCOVERY_BACKEND=etcd
ETCD_ENDPOINTS=http://<B300_NODE_A_IP>:2379
DYN_REQUEST_PLANE=tcp
DYN_EVENT_PLANE=zmq
DYN_TCP_RPC_HOST=${LOCAL_IP}
DYN_EVENT_PLANE_HOST=${LOCAL_IP}
VLLM_HOST_IP=${LOCAL_IP}
VLLM_NIXL_SIDE_CHANNEL_HOST=${LOCAL_IP}
VLLM_NIXL_SIDE_CHANNEL_PORT=5600
VLLM_WORKER_MULTIPROC_METHOD=spawn
UCX_NET_DEVICES=${IB_DEVICES}
UCX_TLS=rc_x,rc,cuda_copy,cuda_ipc
UCX_RNDV_SCHEME=get_zcopy
UCX_RNDV_THRESH=0
NCCL_SOCKET_IFNAME=eth0
GLOO_SOCKET_IFNAME=eth0
NCCL_IB_DISABLE=0
NIXL_LOG_LEVEL=INFO
VLLM_ALLREDUCE_USE_SYMM_MEM=0
VLLM_DISABLED_KERNELS=FlashInferFP8ScaledMMLinearKernel
VLLM_SSM_CONV_STATE_LAYOUT=DS
VLLM_ALLOW_CHUNKED_LOCAL_ATTN_WITH_HYBRID_KV_CACHE=1
DYN_VLLM_APPEND_PREFILL_OUTPUT_TOKENS=0
HF_HOME=/runtime/hf
HF_MODULES_CACHE=/runtime/hf_modules
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
VLLM_CACHE_ROOT=/runtime/vllm
TRITON_CACHE_DIR=/runtime/triton
TORCH_EXTENSIONS_DIR=/runtime/torch_extensions
XDG_CACHE_HOME=/runtime/cache
PYTHONHASHSEED=0
EOF
)
```

On Node A, the explicit local host fields must be **<B300_NODE_A_IP>**. On Node B, they must be **<B300_NODE_B_IP>**. ETCD_ENDPOINTS must be identical on both.

**Leave `DYN_TCP_RESPONSE_STREAM_HOST` unset on both nodes.** In this pinned runtime, setting it to an IP produced `Interface not found`; setting it to `eth0` selected an IPv6 link-local address and caused `Invalid argument (os error 22)`. Leaving it unset uses automatic address detection, which tries IPv4 first. Keep the explicit IP settings for `DYN_TCP_RPC_HOST`, `DYN_EVENT_PLANE_HOST`, `VLLM_HOST_IP` and `VLLM_NIXL_SIDE_CHANNEL_HOST`. [11]

Inspect the file before launching:

```bash
cat /data/nemotron-ultra/common.env
```

NIXL uses UCX; NCCL settings alone do not select its transfer network. The side-channel host must be reachable from the other node. Dynamic Dynamo/UCX ports also require trusted node-to-node access. [9]


## 6. Save the worker launcher

**Run location:** Both nodes / model-specific vLLM settings

This keeps the hybrid Mamba/attention configuration together. The changes from the reference are TP8, 32K context, 32 sequences, an 8192-token batch budget and 0.80 GPU memory utilization. Expert parallelism and MTP are off. [2,3]

```bash
(
set -e
source /data/nemotron-ultra/settings.sh
cat > "$DATA/scripts/worker.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
# Use automatic IPv4-first response-stream address detection.
unset DYN_TCP_RESPONSE_STREAM_HOST
ROLE="${1:?Pass prefill or decode}"
case "$ROLE" in
  prefill|decode) ;;
  *) echo "Invalid role" >&2; exit 2 ;;
esac
PLUGIN=/model/ultra_v3_reasoning_parser.py
test -r /model/config.json
test -r "$PLUGIN"
KV='{"kv_connector":"NixlConnector","kv_role":"kv_both"}'
EVENTS='{"publisher":"zmq","topic":"kv-events",'
EVENTS+='"endpoint":"tcp://127.0.0.1:5571",'
EVENTS+='"enable_kv_cache_events":true}'

exec python3 -m dynamo.vllm \
  --model /model \
  --served-model-name nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4 \
  --tensor-parallel-size 8 \
  --no-enable-expert-parallel \
  --trust-remote-code \
  --kv-cache-dtype fp8 \
  --max-model-len 32768 \
  --max-num-seqs 32 \
  --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.80 \
  --attention-backend FLASHINFER \
  --linear-backend cutlass \
  --moe-backend flashinfer_trtllm \
  --block-size 64 \
  --mamba-backend triton \
  --no-enable-flashinfer-autotune \
  --mamba-cache-mode align \
  --mamba-ssm-cache-dtype bfloat16 \
  --enable-prefix-caching \
  --no-disable-hybrid-kv-cache-manager \
  --async-scheduling \
  --kv-transfer-config "$KV" \
  --disaggregation-mode "$ROLE" \
  --dyn-tool-call-parser qwen3_coder \
  --dyn-reasoning-parser nemotron3 \
  --reasoning-parser-plugin "$PLUGIN" \
  --reasoning-parser nemotron_v3 \
  --kv-events-config "$EVENTS"
SH
)
```

The launcher also unsets the response-stream host override so newly started workers use the same address-selection policy as the frontend. Both roles use kv_both; the disaggregation-mode flag sets the serving role. The engine event socket is local to each worker host. Dynamo republishes events through its event plane. The workers are launched through dynamo.vllm, not as independent public vllm serve APIs.


## 7. Start the Dynamo frontend

**Run location:** Node A only / API at <B300_NODE_A_IP>:8000

Check etcd first. The frontend uses the same local model path for tokenizer discovery. Its runtime directory is separate from the GPU worker, avoiding shared mutable cache directories.

```bash
(
set -e
source /data/nemotron-ultra/settings.sh
require_role prefill
curl -fsS --connect-timeout 5 http://<B300_NODE_A_IP>:2379/health

docker run -d \
  --name dynamo-frontend \
  --network host \
  --user 0 \
  --env-file "$DATA/common.env" \
  -v "$DATA/model:/model:ro" \
  -v "$DATA/runtime/frontend:/runtime" \
  --log-opt max-size=50m \
  --log-opt max-file=3 \
  --entrypoint env "$IMAGE" \
  -u DYN_TCP_RESPONSE_STREAM_HOST \
  python3 -m dynamo.frontend \
  --http-host <B300_NODE_A_IP> \
  --http-port 8000 \
  --router-mode kv \
  --router-kv-events \
  --kv-cache-block-size 64
)
```

### Check frontend startup

```bash
docker logs --tail 100 dynamo-frontend
curl -fsS http://<B300_NODE_A_IP>:8000/health
```

The `env -u` invocation clears `DYN_TCP_RESPONSE_STREAM_HOST` in the frontend process, including any value inherited from the image or environment file. This is the frontend launch configuration that resolved the reported issue.

The model may not appear until the workers register. Frontend health is not evidence that model inference works.

### Frontend endpoint

All API requests go to **http://<B300_NODE_A_IP>:8000**. Node B can use this same URL. The frontend handles routing while the two vLLM workers perform inference. Continue with the worker launch on the next step.


## 8. Start one worker per node

**Run location:** Both nodes / role selected automatically

Run this same block on each node. It starts **ultra-prefill** on Node A and **ultra-decode** on Node B. Both use all eight local GPUs. No second etcd instance is created.

```bash
(
set -e
source /data/nemotron-ultra/settings.sh
test -r "$DATA/model/ultra_v3_reasoning_parser.py"
test -r "$DATA/common.env"
test -r "$DATA/scripts/worker.sh"
curl -fsS --connect-timeout 5 http://<B300_NODE_A_IP>:2379/health

docker run -d \
  --name "ultra-${ROLE}" \
  --gpus all \
  --network host \
  --ipc host \
  --user 0 \
  --device /dev/infiniband \
  --cap-add IPC_LOCK \
  --ulimit memlock=-1:-1 \
  --ulimit stack=67108864:67108864 \
  --env-file "$DATA/common.env" \
  -e DYN_SYSTEM_PORT=8081 \
  -v "$DATA/model:/model:ro" \
  -v "$DATA/runtime/worker:/runtime" \
  -v "$DATA/scripts:/scripts:ro" \
  --log-opt max-size=100m \
  --log-opt max-file=3 \
  --entrypoint bash "$IMAGE" \
  /scripts/worker.sh "$ROLE"
)
```

### Watch initialization on each node

```bash
source /data/nemotron-ultra/settings.sh
docker logs --tail 50 -f "ultra-${ROLE}"
```

Allow time for weight loading and compilation. Ctrl+C exits the log follower without stopping the container. Wait for `VllmWorker ... has been initialized`, `Registered base model ...`, and registration of the local generate endpoint. Use messages from the current startup; older messages do not establish current readiness. A container ID returned by docker run only confirms that Docker created the container.

The NIXL base port 5600 and metrics port 8081 can be the same on these two different hosts. Additional replicas on one host would need distinct port assignments and disjoint GPUs.

### Confirm the expected container on each node

```bash
source /data/nemotron-ultra/settings.sh
docker ps -a --filter "name=ultra-${ROLE}"
```

Node A should show ultra-prefill; Node B should show ultra-decode. If either exits, read its logs before proceeding. Workers are not set to auto-restart during initial validation, so a failure remains visible.


## 9. Test through Dynamo

**Run location:** Either node / all client traffic goes to Node A

First confirm that `/v1/models` contains `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4`. If it returns `"data":[]` after both workers register, read the **frontend logs on Node A** using Step 10 before sending a completion.

The short request below disables thinking to keep the test bounded. The model name must match the served name exactly.

```bash
curl -fsS http://<B300_NODE_A_IP>:8000/v1/models

curl --fail-with-body -sS --max-time 300 \
  http://<B300_NODE_A_IP>:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4",
    "messages": [{
      "role": "user",
      "content": "Explain prefill and decode in three sentences."
    }],
    "max_tokens": 256,
    "temperature": 0,
    "stream": false,
    "chat_template_kwargs": {
      "enable_thinking": false,
      "force_nonempty_content": true
    }
  }' 
```

### Verify transfer activity

Send a longer prompt of several thousand tokens, then repeated prompts with a shared prefix. Watch both worker logs and metrics. Follow with concurrent requests at 4, then 16, and a streaming request. A successful model listing verifies discovery only.

```bash
source /data/nemotron-ultra/settings.sh
curl -fsS "http://${LOCAL_IP}:8081/metrics" |
  grep -Ei 'nixl|transfer|prefill|decode'
docker logs --tail 100 "ultra-${ROLE}"
```

Metric names vary by runtime. An empty grep result alone does not prove transfers failed. Look for NIXL/UCX initialization, intended device selection and transfer counters during traffic, plus successful responses without worker errors.

### Only then increase workload

| Setting | Initial | Next experiments |
| --- | --- | --- |
| Context length | 32768 | 65536, then 131072 |
| Max batched tokens | 8192 | 16384, then 32768 |
| Concurrent sequences | 32 | Increase while measuring latency |
| GPU memory fraction | 0.80 | Toward 0.90 if stable |
| MTP | Disabled | Keep off for initial disaggregation |

Change one setting at a time and rerun tests. Benchmark against aggregated workers; disaggregation does not guarantee higher throughput. A short test does not establish 1M-context readiness.


## 10. Diagnose a failed check

**Run location:** Run diagnostics on the specified node

| Symptom | Action |
| --- | --- |
| etcd: cannot assign requested address | Check that the client listener uses http://0.0.0.0:2379. The advertised client address stays http://<B300_NODE_A_IP>:2379. |
| etcd health fails on Node A | Check container logs and local listening socket below. Fix the service before investigating remote routing. |
| etcd works on A, fails on B | Check private routing and host/provider firewall access to A:2379. A /32 address alone is not a fault. |
| Model missing from /v1/models | Once both workers register, inspect the frontend logs on Node A. Check discovery settings and response-stream errors below. |
| Interface not found: <B300_NODE_A_IP> | Remove DYN_TCP_RESPONSE_STREAM_HOST and launch the frontend with env -u as in Step 7. |
| TcpListender on fe80::... / Invalid argument (os error 22) | The eth0 override selected an IPv6 link-local address. Remove the override; use automatic IPv4-first detection. Do not replace it with eth0 or an IP. |
| No such container / port 8000 refuses connections after cleanup | docker rm removed the service. Complete its launch block: frontend on Node A, prefill on Node A, decode on Node B. |
| Request stalls after prefill | Check reachable NIXL host addresses, allowed node-to-node ports, UCX devices and RDMA access. |
| Mamba/cache or backend errors | Keep the exact image and matching role settings. Capture the first error; avoid mixing engine versions. |
| Container name already in use | The named container already exists. Inspect docker ps -a and its logs before rerunning a launch block. |
| Disk usage climbs | Check model copies, Docker storage and runtime caches. Logs in this guide are size-limited. |

### Frontend diagnostics on Node A

If both workers have registered but the model list is empty, collect the frontend logs before restarting anything:

```bash
docker logs --tail 150 dynamo-frontend 2>&1
docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' dynamo-frontend |
  grep -E '^(DYN_NAMESPACE|DYN_DISCOVERY_BACKEND|ETCD_ENDPOINTS|DYN_TCP_RESPONSE_STREAM_HOST)='
```

Expected discovery settings are `DYN_NAMESPACE=nemotron-ultra`, `DYN_DISCOVERY_BACKEND=etcd`, and `ETCD_ENDPOINTS=http://<B300_NODE_A_IP>:2379`. The corrected common.env omits `DYN_TCP_RESPONSE_STREAM_HOST`; `env -u` additionally clears it before the frontend starts. Docker inspect lists the configured container environment, which can differ from the process environment after `env -u`.

### Existing deployment: replace only the frontend to apply the confirmed fix

**Node A only. Skip this subsection for a fresh installation or an already working frontend.** Keep etcd and both GPU workers running while checking frontend recovery. This block removes the old frontend and immediately creates its replacement; do not run only its stop/remove lines.

```bash
(
set -e
source /data/nemotron-ultra/settings.sh
require_role prefill
sed -i.bak '/^DYN_TCP_RESPONSE_STREAM_HOST=/d' "$DATA/common.env"

docker stop -t 30 dynamo-frontend
docker rm dynamo-frontend

docker run -d \
  --name dynamo-frontend \
  --network host \
  --user 0 \
  --env-file "$DATA/common.env" \
  -v "$DATA/model:/model:ro" \
  -v "$DATA/runtime/frontend:/runtime" \
  --log-opt max-size=50m \
  --log-opt max-file=3 \
  --entrypoint env "$IMAGE" \
  -u DYN_TCP_RESPONSE_STREAM_HOST \
  python3 -m dynamo.frontend \
  --http-host <B300_NODE_A_IP> \
  --http-port 8000 \
  --router-mode kv \
  --router-kv-events \
  --kv-cache-block-size 64
)
```

After about 15 seconds, check:

```bash
docker logs --tail 100 dynamo-frontend 2>&1
curl -sS http://<B300_NODE_A_IP>:8000/v1/models
```

This recovery block assumes the frontend container still exists. If it was already removed, run Step 7 directly. It does not restart the workers or change their current process environments. For future worker launches, use the common.env and worker launcher from Steps 5 and 6. If inference later fails, collect both worker logs before making further changes.

### etcd diagnostics on Node A

```bash
docker ps -a --filter name=dynamo-etcd
docker logs --tail 50 dynamo-etcd
sudo ss -lntp 'sport = :2379'
curl -v --connect-timeout 5 http://<B300_NODE_A_IP>:2379/health
```

### Connection diagnostics on Node B

```bash
ip route get <B300_NODE_A_IP>
curl -v --connect-timeout 5 http://<B300_NODE_A_IP>:2379/health
```

TCP failures reaching etcd do not diagnose InfiniBand. Likewise, a working etcd connection does not prove RDMA. Keep the IP control path and the RDMA data path checks separate.

For this initial setup, expose the API only on the private network. If accessing it from your laptop, an SSH tunnel to Node A can forward local port 8000. Add authentication/TLS and service redundancy before broader production access.


## References and operating notes

**Run location:** Version scope / source links

**Version scope:** Dynamo 1.4.0 at the exact NVIDIA recipe digest; the published compatibility matrix lists vLLM 0.26.0 and CUDA 13.0 for this release. Model revision is explicitly pinned. Both nodes must use the same settings for model revision, tensor parallelism and cache layout. [3,4]

**Adaptation:** the official recipe is Kubernetes-based and includes qualified B200/GB200/H200 profiles. This document adapts its engine settings to two Docker hosts with B300 GPUs and TP8 workers. It does not claim that NVIDIA benchmarked this exact topology. [2,3]

**Known output limitation:** the pinned Ultra guide documents issues with thinking enabled together with constrained JSON output or forced tool choice. Start with thinking disabled for those cases and validate returned structures. [2]

[1] [NVIDIA NVFP4 checkpoint and pinned revision](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4/tree/252a02f921642313abde19b29a723a16602fe25e)

[2] [NVIDIA Dynamo: Nemotron 3 Ultra deployment profiles](https://docs.nvidia.com/dynamo/dev/recipes/nemotron-3-ultra)

[3] [NVIDIA reference: Blackwell disaggregated worker manifest](https://github.com/ai-dynamo/dynamo/blob/main/recipes/nemotron-3-ultra/vllm/disagg-b200-agentic-256K/deploy.yaml)

[4] [Dynamo 1.4.0 compatibility matrix](https://docs.nvidia.com/dynamo/v1.4.0/reference/compatibility)

[5] [Linux RDMA perftest commands and options](https://github.com/linux-rdma/perftest/blob/master/man/perftest.1)

[6] [NVIDIA Ultra model-cache preparation](https://github.com/ai-dynamo/dynamo/blob/main/recipes/nemotron-3-ultra/model-cache/README.md)

[7] [Dynamo 1.4.0 request transport](https://docs.nvidia.com/dynamo/v1.4.0/knowledge-base/concepts/communication-planes/request-plane)

[8] [Dynamo 1.4.0 event transport](https://docs.nvidia.com/dynamo/v1.4.0/knowledge-base/concepts/communication-planes/event-plane)

[9] [vLLM NIXL configuration and network transport](https://docs.vllm.ai/en/latest/features/nixl_connector_usage/)

[10] [NVIDIA Container Toolkit installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

[11] [Dynamo 1.4.0 response-stream address selection](https://github.com/ai-dynamo/dynamo/blob/v1.4.0/lib/runtime/src/pipeline/network/tcp/server.rs)

### What the supplied hardware output established

Each node showed eight idle B300 GPUs with 275040 MiB per GPU, NV18 GPU links, about 2.6 TiB available RAM, and 973 GiB free on the root filesystem. The selected eight InfiniBand ports on each node showed active 800 Gb/s links. These are inventory observations, not throughput or end-to-end health measurements.

Prepared 29 September 2026. Remote source pages can change; retain the image digest, model revision and this runbook with any benchmark results. This revision incorporates the supplied startup logs and your reported frontend recovery. Commands were checked for shell syntax locally; the assistant did not execute installation or inference commands on the servers.
