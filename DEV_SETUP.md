# VMS — Local Dev Setup

## Services overview

| Service | Container | Host port | Notes |
|---|---|---|---|
| PostgreSQL (dev) | `vms-postgres` | 5432 | pgvector/pgvector:pg16 |
| PostgreSQL (test) | `vms-test-db` | 5434 | used by `pytest` only |
| Redis | `vms-redis` | 6379 | |
| Triton (GPU inference) | `vms-triton` | 8000 HTTP / 8001 gRPC / 8002 metrics | occupies 8000-8002; optional — ORT used when `VMS_GPU_TRITON_URL` is empty |
| FastAPI backend | — (uvicorn) | **8080** | avoids Triton range |
| React frontend | — (Vite) | 5173 | proxies `/api` → 8080 |

## Database credentials

```
Host:     localhost:5432
Database: vms
Username: vms
Password: vms
URL:      postgresql://vms:vms@localhost:5432/vms
```

## Admin login (dev)

```
Username: admin
Password: admin123
URL:      http://localhost:5173/login
```

## Start everything

### 1. Start Docker services (if not already running)

```cmd
docker start vms-postgres vms-redis
```

**Optional — start Triton GPU inference server** (requires NVIDIA GPU + image already pulled):
```cmd
docker start vms-triton
```

If `vms-triton` doesn't exist yet, create it (single line, run in cmd.exe):
```cmd
docker run --rm -d --name vms-triton --gpus all --shm-size=4g -p 8000:8000 -p 8001:8001 -p 8002:8002 -v "F:\facial_recognistion\facial_recognistion\models\triton_repo:/models" nvcr.io/nvidia/tritonserver:24.05-py3 tritonserver --model-repository=/models --strict-model-config=false
```

Verify all 4 models are READY: `docker logs vms-triton --tail 10`

First-time only — create the dev postgres container:
```cmd
docker run -d --name vms-postgres -e POSTGRES_USER=vms -e POSTGRES_PASSWORD=vms -e POSTGRES_DB=vms -p 5432:5432 pgvector/pgvector:pg16
```

### 2. Start the backend (new terminal)

```powershell
cd F:\facial_recognistion\facial_recognistion
.\venv\Scripts\activate
$env:VMS_DB_URL="postgresql://vms:vms@localhost:5432/vms"
$env:VMS_REDIS_URL="redis://localhost:6379"
$env:VMS_JWT_SECRET="dev-secret-change-in-production"
uvicorn vms.api.main:socket_app --reload --port 8080
```

### 3. Start the frontend (second terminal)

```powershell
cd F:\facial_recognistion\facial_recognistion\frontend
pnpm dev
```

Open http://localhost:5173

## First-time DB setup

Run once after creating the postgres container:

```powershell
# With env vars set (step 2 above)
alembic upgrade head
python scripts/seed_admin_user.py
```

## Run tests

```powershell
# Backend (unit + integration)
pytest --cov=vms --cov-report=term-missing -v

# Frontend
cd frontend
pnpm test:run
```

## Check Docker container status

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
