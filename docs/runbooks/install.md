# VMS Installation Runbook

**Target:** Ubuntu 22.04 LTS or Windows Server 2022 with NVIDIA GPU
**Time:** ~45 minutes on a clean server

---

## 1. Hardware Prerequisites

| Component | Minimum | Recommended |
|---|---|---|
| GPU | NVIDIA RTX 3080 (10 GB VRAM) | NVIDIA A4000 (16 GB VRAM) |
| CPU | 8-core, 3 GHz | 16-core, 3.5 GHz |
| RAM | 32 GB | 64 GB |
| Storage | 500 GB SSD | 2 TB NVMe (for video thumbnails) |
| Network | 1 Gbps | 10 Gbps (for 52-camera deployments) |

---

## 2. Software Prerequisites

### Ubuntu 22.04

1. Install NVIDIA driver >= 525:
   ```bash
   sudo apt install nvidia-driver-525 -y
   sudo reboot
   nvidia-smi  # verify
   ```
2. Install Docker + nvidia-container-toolkit:
   ```bash
   curl -fsSL https://get.docker.com | sh
   distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
       sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" | \
       sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt update && sudo apt install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```
3. Install Python 3.10+:
   ```bash
   sudo apt install python3.10 python3.10-venv python3-pip -y
   ```

### Windows Server 2022

1. Install NVIDIA Game Ready or Studio driver >= 525 from nvidia.com
2. Install Docker Desktop with WSL2 backend
3. Install Python 3.10 from python.org

---

## 3. Deploy with Docker Compose (Recommended)

1. Copy the VMS release archive to the server and extract it.

2. Create the environment file:
   ```bash
   cp .env.example .env
   # Edit .env — set VMS_DB_URL, VMS_JWT_SECRET, VMS_REDIS_URL
   ```

3. Download ML models:
   ```bash
   python -m vms.cli models download
   python -m vms.cli models verify
   ```

4. Start all services:
   ```bash
   docker compose up -d
   ```

5. Apply migrations:
   ```bash
   docker compose exec vms-app alembic upgrade head
   ```

6. Create the first admin user:
   ```bash
   docker compose exec vms-app python -m vms.cli users create --admin \
       --email admin@example.com --password "ChangeMe123!"
   ```

---

## 4. Bare-Metal Install (Advanced)

1. Install system dependencies:
   ```bash
   sudo apt install libpq-dev redis-server postgresql-16 -y
   ```

2. Create a venv and install:
   ```bash
   python3.10 -m venv /opt/vms/venv
   /opt/vms/venv/bin/pip install -e ".[prod]"
   ```

3. Configure environment variables in `/etc/vms/env`:
   ```
   VMS_DB_URL=postgresql://vms:secret@localhost:5432/vms
   VMS_JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
   VMS_REDIS_URL=redis://localhost:6379/0
   ```

4. Install systemd units (provided in `scripts/systemd/`):
   ```bash
   sudo cp scripts/systemd/*.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable vms-app vms-worker
   sudo systemctl start vms-app vms-worker
   ```

---

## 5. Post-Install Verification

```bash
curl http://localhost:8000/api/health
# Expected: {"status": "ok", "db": "connected", "redis": "connected"}
```

Check GPU inference is available:
```bash
docker compose exec vms-app python -c "import onnxruntime; print(onnxruntime.get_available_providers())"
# Expected output includes: 'CUDAExecutionProvider'
```

---

## 6. Common Install Errors

| Error | Cause | Fix |
|---|---|---|
| `CUDA out of memory` | GPU VRAM too low | Reduce `--num-cameras` or upgrade GPU |
| `Connection refused :5432` | PostgreSQL not started | `sudo systemctl start postgresql` |
| `pgvector extension not found` | Wrong PostgreSQL image | Use `pgvector/pgvector:pg16` Docker image |
| `OSError: [Errno 22] shm` | SHM size limits on Linux | `echo 'kernel.shmmax=2147483648' >> /etc/sysctl.conf && sysctl -p` |
| `ONNX model file not found` | Models not downloaded | Run `python -m vms.cli models download` |
