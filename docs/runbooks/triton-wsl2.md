# Triton Inference Server — WSL2 Deployment Runbook

**Operator runbook for VMS Phase 6c.**
**Applies to:** plant-floor VMS deployments using Triton for cross-camera GPU batching.

---

## Overview

Triton ships as a Linux Docker image with no native Windows build. This runbook covers
two deployment paths depending on which Docker runtime is available on the host.

### Path A — Docker Desktop (developer machines, pilot sites)

If Docker Desktop is installed on the Windows host, Triton can be run directly from
PowerShell. Docker Desktop's WSL2 backend provides GPU passthrough with no additional
NVIDIA toolkit installation required.

```
Windows process (VMS)
  │
  │  VMS_GPU_TRITON_URL=localhost:8001  (gRPC)
  ▼
Docker Desktop (Windows)
  └── nvcr.io/nvidia/tritonserver container
        ├── GPU: via Docker Desktop NVIDIA passthrough
        └── models: bind-mount from F:\...\models\triton_repo
```

This is the **recommended path for developer and pilot installations.**
Docker Desktop must have GPU support enabled (Settings → Resources → GPU acceleration).

### Path B — Rootless Docker in WSL2 (production / enterprise customer sites)

For production deployments on customer hardware, Docker Desktop has a commercial license
restriction for large enterprises (> 250 employees or > $10M revenue). Use rootless Docker
Engine installed inside WSL2 instead.

```
Windows process (VMS)
  │
  │  VMS_GPU_TRITON_URL=localhost:8001  (gRPC)
  ▼
WSL2 Ubuntu 22.04
  └── rootless Docker daemon
        └── nvcr.io/nvidia/tritonserver container
              ├── GPU: via NVIDIA Container Toolkit (WSL2 passthrough)
              └── models: bind-mount from /mnt/c/vms/models/triton_repo
```

Sections 1–3 cover prerequisites and Docker setup. Section 5 shows both run commands.

---

`VMS_GPU_TRITON_URL=""` (empty) keeps the in-process ORT/TRT EP — nothing else changes.
Setting it to `localhost:8001` routes all four ONNX models through Triton with no other
code changes.

---

## 1. Windows Host Prerequisites

### 1.1 NVIDIA driver ≥ 535

WSL2 GPU passthrough requires NVIDIA driver ≥ 535 on the **Windows host**.  
The driver version visible inside WSL2 (`nvidia-smi`) mirrors the host driver —
do not install a CUDA toolkit inside WSL2; it is not needed.

Verify on the host (PowerShell):

```powershell
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
```

Expected output example:

```
RTX 2000 Ada Generation Laptop GPU, 560.94, 16376 MiB
```

Minimum: `driver_version ≥ 535`. Upgrade via NVIDIA GeForce Experience or
direct download from nvidia.com if the version is lower.

### 1.2 WSL2 with Ubuntu 22.04

```powershell
wsl --install -d Ubuntu-22.04
wsl --set-version Ubuntu-22.04 2     # ensure WSL2, not WSL1
wsl --set-default Ubuntu-22.04
```

Reboot after the first install. Verify WSL2 mode:

```powershell
wsl -l -v
# NAME           STATE   VERSION
# Ubuntu-22.04   Running 2
```

### 1.3 Verify GPU passthrough inside WSL2

```bash
# inside WSL2 terminal
nvidia-smi
```

Expected: GPU name, driver version (matching host), and memory — identical to the host
`nvidia-smi` output. If this fails, the WSL2 kernel is too old; update Windows:

```powershell
# PowerShell (host)
wsl --update
```

---

## 2. WSL2 Memory Configuration *(both paths)*

WSL2's default memory ballooning can starve a Triton container on a server that is
also running PostgreSQL, Redis, and the VMS inference process simultaneously.
Set explicit limits in `%USERPROFILE%\.wslconfig` on the Windows host.

**Template (edit and save as `C:\Users\<you>\.wslconfig`):**

```ini
[wsl2]
# Explicit memory cap — WSL2 will not balloon beyond this.
# Rule of thumb: host RAM - 4 GB (leave 4 GB for Windows + VMS services).
# For a 16 GB host: 12 GB. For a 32 GB host: 26 GB.
memory=12GB

# Swap: set equal to memory, capped at 16 GB.
# Triton model load + TRT engine compilation can spike working set briefly.
swap=12GB

# Increase if Triton reports "mmap failed" or OOM during model load.
# Default 8 MB is insufficient for large model repos.
kernelCommandLine=hugepages=512
```

After editing, restart WSL2:

```powershell
wsl --shutdown
wsl -d Ubuntu-22.04
```

---

## 3. Rootless Docker in WSL2 + NVIDIA Container Toolkit *(Path B only)*

Skip this section if using Docker Desktop (Path A). Rootless Docker avoids the Docker
Desktop commercial license restriction that applies to enterprise customers
(> 250 employees or > $10M revenue).

### 3.1 Install Docker Engine (rootless mode)

```bash
# inside WSL2 — as a regular user (not root)
sudo apt-get update
sudo apt-get install -y uidmap fuse-overlayfs slirp4netns

# Install Docker engine
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh --dry-run   # review first
sh get-docker.sh

# Configure rootless mode
dockerd-rootless-setuptool.sh install

# Add to shell profile so Docker client finds the rootless socket
echo 'export DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock' >> ~/.bashrc
source ~/.bashrc

# Verify
docker run --rm hello-world
```

### 3.2 Install NVIDIA Container Toolkit

```bash
# inside WSL2
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure for rootless Docker
nvidia-ctk runtime configure --runtime=docker --config ~/.config/docker/daemon.json
# Restart rootless dockerd
systemctl --user restart docker

# Verify GPU access inside a container
docker run --rm --gpus all ubuntu:22.04 nvidia-smi
```

Expected: `nvidia-smi` output inside the container matching the host GPU.

---

## 4. Build the Triton Model Repository

The model repository is generated by `scripts/build_triton_repo.py` (Task 2).
Run this from the Windows host (inside the project directory):

```powershell
# PowerShell — Windows host
python scripts/build_triton_repo.py --out models/triton_repo
```

This creates:

```
models/triton_repo/
├── scrfd_10g_bnkps/
│   ├── config.pbtxt
│   └── 1/model.onnx
├── adaface_ir101_webface12m/
│   ├── config.pbtxt
│   └── 1/model.onnx
├── transreid_body_msmt17/
│   ├── config.pbtxt
│   └── 1/model.onnx
└── osnet_ain_x1_0_msmt17/
    ├── config.pbtxt
    └── 1/model.onnx
```

---

## 5. Start the Triton Server

### 5.1 Choose the Triton image tag

The tag pins TRT and CUDA versions simultaneously. See §6.4 compatibility matrix
below for tested combinations. For CUDA 12.4 hosts with TRT 10.x:

```
nvcr.io/nvidia/tritonserver:24.05-py3
```

Pull once (this is ~10 GB):

```bash
# inside WSL2
docker pull nvcr.io/nvidia/tritonserver:24.05-py3
```

### 5.2 Docker run command

**Path A — Docker Desktop (PowerShell on Windows host):**

```powershell
# PowerShell — Windows host
$TRITON_REPO = "F:\facial_recognistion\facial_recognistion\models\triton_repo"
$TRITON_IMAGE = "nvcr.io/nvidia/tritonserver:24.05-py3"

docker run --rm -d `
  --name vms-triton `
  --gpus all `
  --shm-size=4g `
  -p 8000:8000 `
  -p 8001:8001 `
  -p 8002:8002 `
  -v "${TRITON_REPO}:/models" `
  $TRITON_IMAGE `
  tritonserver `
    --model-repository=/models `
    --strict-model-config=false `
    --log-verbose=0
```

**Path B — Rootless Docker (inside WSL2):**

The `models/triton_repo` directory lives on the Windows filesystem. WSL2 exposes
Windows drives at `/mnt/<drive>/`:

```bash
# inside WSL2 — adjust path to match your project directory
TRITON_REPO="/mnt/f/facial_recognistion/facial_recognistion/models/triton_repo"
TRITON_IMAGE="nvcr.io/nvidia/tritonserver:24.05-py3"

docker run --rm -d \
  --name vms-triton \
  --gpus all \
  --shm-size=4g \
  -p 8000:8000 \
  -p 8001:8001 \
  -p 8002:8002 \
  -v "${TRITON_REPO}:/models" \
  "${TRITON_IMAGE}" \
  tritonserver \
    --model-repository=/models \
    --strict-model-config=false \
    --log-verbose=0
```

Ports:
- `8000` — HTTP management (optional; used by `tritonserver --metrics-port`)
- `8001` — gRPC inference endpoint (the one VMS uses)
- `8002` — Prometheus metrics

`--shm-size=4g`: Triton uses shared memory for zero-copy transfers between processes.
4 GB is sufficient for 4 models; increase to 8 GB if adding more models.

`--strict-model-config=false`: lets Triton infer missing config fields from the ONNX graph.

### 5.3 Verify server startup

```bash
# inside WSL2
docker logs vms-triton -f
# Wait for: "Started GRPCInferenceService at 0.0.0.0:8001"

# Health check (requires curl)
curl -s http://localhost:8000/v2/health/ready && echo "READY"
```

Each model should show `READY` in the logs:

```
I  Model 'scrfd_10g_bnkps' loaded.
I  Model 'adaface_ir101_webface12m' loaded.
I  Model 'transreid_body_msmt17' loaded.
I  Model 'osnet_ain_x1_0_msmt17' loaded.
```

---

## 6. Connect VMS to Triton

Set the environment variable before starting the VMS process (PowerShell):

```powershell
$env:VMS_GPU_TRITON_URL = "localhost:8001"
```

Or in `.env`:

```env
VMS_GPU_TRITON_URL=localhost:8001
```

`VMS_GPU_TRITON_URL=""` (empty, the default) keeps the in-process ORT/TRT EP — no Triton.

Verify the connection at startup: VMS logs emit at INFO level:

```
Triton backend active — host=localhost:8001
```

---

## 7. TRT Engine-Cache Invalidation

Triton caches TensorRT engine plans in the model repository directory (alongside each
`config.pbtxt`). **TRT plans are GPU-driver-version specific.** After a Windows
NVIDIA driver upgrade, cached plans from the prior driver are silently stale and will
cause inference errors or degraded accuracy.

**After any NVIDIA driver upgrade:**

1. Stop the Triton container: `docker stop vms-triton`
2. Delete TRT plan cache directories:
   ```powershell
   # PowerShell — Windows host
   Remove-Item -Recurse -Force C:\vms\models\triton_repo\*\trt_cache\
   ```
3. Restart Triton — it recompiles plans from ONNX on first load (adds ~2–5 min to startup).
4. Verify all four models show `READY` in logs before routing live cameras.

Same procedure applies after a CUDA toolkit version change or a Triton image tag upgrade
(new Triton image may bundle a different TRT version).

This is the same engine-cache invalidation behaviour documented in the Phase 6b TensorRT
runbook — Triton simply manages the cache inside the container rather than in-process.

---

## 8. §6.4 Compatibility Matrix

Fill during MVP hardware sessions. Add rows for each distinct Windows/driver/Triton
combination tested. Do not ship Triton as a supported configuration without at least
one ✓ row with a sustained-load result.

"Works" = Triton starts cleanly + GPU passthrough confirmed + `VMS_GPU_TRITON_URL`
smoke-test passes ≥3 live cameras at steady state.

| Windows OS | NVIDIA Driver | Docker Runtime | Triton Image | CUDA in Container | ORT Backend Ver | Status | Notes |
|---|---|---|---|---|---|---|---|
| Windows 11 Pro 23H2 (26200) | 595.71 | Docker Desktop 29.5.3 (Path A) | `24.05-py3` | 12.4 | 1.18.x | ✓ confirmed | All 4 models READY; GPU passthrough confirmed 2026-06-26 |
| Windows 11 Pro 23H2 (26200) | 560.94 | Docker Desktop (Path A) | `24.05-py3` | 12.4 | 1.18.x | ○ untested | |
| Windows Server 2022 21H2 | 535.x | rootless Docker WSL2 (Path B) | `24.05-py3` | 12.4 | 1.18.x | ○ untested | |
| Windows Server 2022 21H2 | 555.x | rootless Docker WSL2 (Path B) | `24.05-py3` | 12.4 | 1.18.x | ○ untested | |
| Windows Server 2022 21H2 | 555.x | rootless Docker WSL2 (Path B) | `24.08-py3` | 12.6 | 1.19.x | ○ untested | |

**Triton image tag guide:**
- `24.05-py3` → TRT 10.0, CUDA 12.4, ORT 1.18 backend — target for CUDA 12.4 hosts
- `24.08-py3` → TRT 10.2, CUDA 12.6, ORT 1.19 backend — use on CUDA 12.6+ hosts
- Always use the same CUDA major version in the container as on the host driver

**ORT backend version note:** The Triton ORT backend version determines the supported
ONNX opset. OSNet ONNX is exported at opset 17 (requires ORT ≥ 1.18). Do not use
Triton images older than `24.05-py3` — ORT 1.17 and earlier do not support opset 17.

Fill the Status column during MVP:
- `○ untested` — not yet tested on this combination
- `✓ confirmed` — fully working; record exact Triton image tag and sustained-load result
- `✗ incompatible` — add reason (e.g. "WSL2 GPU passthrough fails — host driver 530 too old")

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `nvidia-smi` missing inside WSL2 | WSL2 kernel too old | `wsl --update` on Windows host |
| Triton container OOM during model load | WSL2 memory limit too low | Increase `memory=` in `.wslconfig`; restart WSL2 |
| `Failed to initialize TensorRT` on model load | Stale TRT plans from prior driver | Delete `trt_cache/` dirs; restart Triton |
| `VMS_GPU_TRITON_URL` set but VMS uses ORT | URL is empty or whitespace | Confirm `VMS_GPU_TRITON_URL=localhost:8001` (no quotes, no trailing slash) |
| gRPC connection refused | Triton not yet ready | Wait for `Started GRPCInferenceService` in `docker logs` |
| Model shows `UNAVAILABLE` in Triton logs | ONNX file missing or wrong path | Verify `models/triton_repo/<model>/1/model.onnx` exists; re-run `build_triton_repo.py` |
| "shape expected by model is [1,3,640,640]" error | `config.pbtxt` sets `max_batch_size > 0` for a fixed-batch model | Re-run `build_triton_repo.py` — it auto-detects fixed vs dynamic batch and sets `max_batch_size=0` for fixed-batch models (SCRFD, PPE) |
| `mmap failed` in Triton container | `--shm-size` too small | Increase to `--shm-size=8g` |
| Triton port 8001 unreachable from Windows | WSL2 localhost forwarding not active | Verify `localhost` works: `curl http://localhost:8000/v2/health/ready` from PowerShell |

### WSL2 localhost forwarding note

Since WSL2 kernel 5.15.90+ (Windows 11 22H2+), `localhost` on the Windows host
reaches WSL2 services by default via the mirrored networking mode. If using an older
kernel or Windows Server 2019, use the WSL2 IP directly:

```bash
# inside WSL2 — get the IP
ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1
```

Then set `VMS_GPU_TRITON_URL=<wsl2-ip>:8001` in `.env`.

---

## 10. Systemd Service (optional — production hardening)

For production sites, run Triton as a systemd user service inside WSL2 so it starts
automatically when WSL2 boots:

```bash
# inside WSL2: create ~/.config/systemd/user/vms-triton.service
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/vms-triton.service <<'EOF'
[Unit]
Description=VMS Triton Inference Server
After=docker.service
Requires=docker.service

[Service]
Restart=always
RestartSec=5
ExecStartPre=-/usr/bin/docker stop vms-triton
ExecStartPre=-/usr/bin/docker rm vms-triton
ExecStart=/usr/bin/docker run --rm --name vms-triton \
  --gpus all \
  --shm-size=4g \
  -p 8000:8000 -p 8001:8001 -p 8002:8002 \
  -v /mnt/c/vms/models/triton_repo:/models \
  nvcr.io/nvidia/tritonserver:24.05-py3 \
  tritonserver --model-repository=/models --strict-model-config=false
ExecStop=/usr/bin/docker stop vms-triton

[Install]
WantedBy=default.target
EOF

systemctl --user enable vms-triton
systemctl --user start vms-triton
systemctl --user status vms-triton
```

Enable WSL2 systemd if not already active (add to `/etc/wsl.conf` inside WSL2):

```ini
[boot]
systemd=true
```

Then restart WSL2: `wsl --shutdown` from PowerShell.
