# Runbook — OSKAR VM Deployment
# Target: apac-plm-ops.srxglobal.local (Ubuntu 24.04 LTS, VMware)
# Owner: Lead Engineer (hsalazar)
# Last updated: 2026-06-02 (Sprint 5 complete — staging stack live)
#
# This runbook covers first deployment (staging) and production promotion.
# Harbor installation is a separate prerequisite: docs/runbooks/harbor-installation.md

---

## Overview

| Item | Value |
|------|-------|
| VM hostname | `apac-plm-ops.srxglobal.local` |
| VM IP | `10.131.1.10` |
| VM specs | 4 CPUs / 16 GB RAM / 100 GB storage |
| Harbor registry | `10.131.1.10` (HTTP port 80 — insecure mode) |
| Staging backend port | `8001` |
| Staging frontend port | `3001` |
| Production backend port | `8000` |
| Production frontend port | `3000` |
| Compose files | `docker/docker-compose.staging.yml`, `docker/docker-compose.yml` |
| Env file on VM | `/opt/oskar/.env.staging` |
| App directory on VM | `/opt/oskar` |
| Source on VM | `/opt/oskar-src/Oskar-master` |
| MOVEX CONO | `300` = staging/UAT, `100` = production only |

---

## Prerequisites

Before running this runbook, confirm:

- [ ] Harbor installed and running — `sudo docker ps` on VM shows all harbor-* containers healthy
- [ ] `oskar` project created in Harbor UI (`http://10.131.1.10` → New Project → `oskar`, public)
- [ ] SSH access to VM: `ssh administrator@10.131.1.10` (port 22)
- [ ] Node.js installed on VM: `node -v && npm -v` (needed only for lock file regen)
- [ ] Docker daemon configured with insecure registry on the VM (see Step 0)

---

## Step 0 — Configure Docker Insecure Registry on VM

Harbor runs HTTP-only (no TLS). Docker must be told to trust it:

```bash
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "insecure-registries": ["10.131.1.10", "10.131.1.10:80"]
}
EOF
sudo systemctl restart docker
docker info | grep -A5 "Insecure Registries"
```

Expected output includes `10.131.1.10` in the insecure registries list.

> **Note:** This step is persistent across reboots (unlike Rancher Desktop on Windows, which
> resets `/etc/docker/daemon.json` on every restart).

---

## Step 1 — Get Source onto VM

Download the GitHub zip and extract on the VM:

```bash
# On VM — download and extract
wget https://github.com/<org>/Oskar/archive/refs/heads/master.zip -O /tmp/oskar.zip
sudo mkdir -p /opt/oskar-src
sudo unzip /tmp/oskar.zip -d /opt/oskar-src
sudo chown -R administrator:administrator /opt/oskar-src
cd /opt/oskar-src/Oskar-master
```

> **Why this approach:** The corporate transparent proxy blocks direct Docker pushes from Windows
> to the VM's private IP range. Building images on the VM itself bypasses the proxy entirely.
> See LL-002 for the full investigation.

---

## Step 2 — Regenerate Frontend Lock File

The `package-lock.json` may be out of sync with `package.json` after dependency updates.
`npm ci` (used in the Docker build) requires them to be in sync.

```bash
cd /opt/oskar-src/Oskar-master/frontend
npm install
```

This only needs to run when the lock file is stale. If `docker build` succeeds at the `npm ci`
step, skip this.

---

## Step 3 — Log In to Harbor from VM

```bash
docker login 10.131.1.10 -u admin -p <harbor-password>
```

Expected: `Login Succeeded`

> If Harbor containers are down, start them first:
> ```bash
> cd /opt/harbor && sudo docker compose up -d
> ```

---

## Step 4 — Build and Push Images

```bash
cd /opt/oskar-src/Oskar-master

# Backend
docker build -t 10.131.1.10/oskar/oskar-app:v0.1.0 -f Dockerfile .
docker push 10.131.1.10/oskar/oskar-app:v0.1.0

# Frontend
docker build -t 10.131.1.10/oskar/oskar-frontend:v0.1.0 -f frontend/Dockerfile ./frontend
docker push 10.131.1.10/oskar/oskar-frontend:v0.1.0
```

Confirm both images appear in Harbor:
`http://10.131.1.10` → Projects → oskar → Repositories

> **Frontend image notes:**
> - Uses `nginxinc/nginx-unprivileged:alpine` (not `nginx:alpine`) — runs as non-root,
>   compatible with `read_only: true` and `cap_drop: ALL` in the compose file.
> - Listens on port 8080 internally; compose maps `3001:8080`.

---

## Step 5 — Create App Directory and Env File

```bash
sudo mkdir -p /opt/oskar
sudo tee /opt/oskar/.env.staging > /dev/null <<'EOF'
REGISTRY=10.131.1.10/oskar
TAG=v0.1.0

POSTGRES_PASSWORD=oskar_staging_pass
MOVEX_API_URL=
MOVEX_API_KEY=
MOVEX_CONO=300
CELERY_SECURITY_KEY=change-me-celery-key

SMTP_HOST=10.10.0.155
SMTP_PORT=25
SMTP_SENDER=oskar@srxglobal.com

LDAP_SERVER=
LDAP_BASE_DN=
LDAP_BIND_DN=
LDAP_BIND_PW=
LDAP_ENABLED=false

JWT_SECRET_KEY_STAGING=change-me-jwt-secret-staging-64chars
REFRESH_TOKEN_SECRET_STAGING=change-me-refresh-secret-staging-64chars
OSKAR_ENV=staging
EOF
```

> Replace placeholder values with real secrets before go-live. Generate keys with:
> `openssl rand -hex 32`

---

## Step 6 — Copy Compose File and Start Stack

```bash
sudo cp /opt/oskar-src/Oskar-master/docker/docker-compose.staging.yml /opt/oskar/

cd /opt/oskar
sudo docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

Verify all containers are up:

```bash
sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected:
```
oskar-app-staging      Up (healthy)   0.0.0.0:8001->8000/tcp
oskar-worker-staging   Up             8000/tcp
oskar-beat-staging     Up             8000/tcp
oskar-frontend-staging Up             0.0.0.0:3001->8080/tcp
oskar-db-staging       Up (healthy)   0.0.0.0:5433->5432/tcp
```

> Worker and beat show no healthcheck (by design — Celery has no HTTP health endpoint).
> They will show `health: starting` briefly, then `Up` with no health status — this is normal.

---

## Step 7 — Run Migrations

```bash
sudo docker exec -w /app oskar-app-staging alembic upgrade head
```

Expected: Alembic prints each migration from `0001` to the latest revision. No errors.

The image includes `alembic/` and `alembic.ini` — no fallback container needed.

---

## Step 8 — Seed Demo Data

The container runs `read_only: true`, so scripts cannot be copied in via `docker cp`.
Use a one-off container with the source mounted as a volume:

```bash
sudo docker run --rm \
  --network oskar-staging-network \
  -w /app \
  -e DATABASE_URL=postgresql+asyncpg://oskar:oskar_staging_pass@oskar-db-staging:5432/oskar_staging \
  -v /opt/oskar-src/Oskar-master/scripts:/app/scripts:ro \
  10.131.1.10/oskar/oskar-app:v0.1.0 \
  python scripts/seed_demo.py
```

Expected: prints 7 ECNs created across all workflow stages (Draft → Closed).

Demo users (any password in dev auth mode):

| Username | Role |
|----------|------|
| `hsalazar` | Originator + Document Controller |
| `eng_user` | Senior Engineer |
| `qm_user` | Quality Manager |
| `dc_user` | Document Controller |

---

## Step 9 — Smoke Test

```bash
# Health check
curl http://localhost:8001/health
# Expected: {"status":"ok"}

# Login
curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"hsalazar","password":"password"}' | python3 -m json.tool

# ECN list (use token from above)
TOKEN="<access_token>"
curl -s http://localhost:8001/api/v1/ecn/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/
# Expected: 200
```

---

## Step 10 — IIS Reverse Proxy (SRXWEBAPP1)

Create a new IIS site or virtual application on SRXWEBAPP1:

| Item | Value |
|------|-------|
| Hostname | `oskar.srxglobal.local` |
| Backend proxy | `http://10.131.1.10:8001` (FastAPI) |
| Frontend proxy | `http://10.131.1.10:3001` (nginx) |

Route `/api/*` to the backend, all other requests to the frontend.

---

## Step 11 — Enable Auto-Start on Reboot

```bash
sudo tee /etc/systemd/system/oskar-staging.service <<'EOF'
[Unit]
Description=OSKAR Staging Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/oskar
ExecStart=/usr/bin/docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
ExecStop=/usr/bin/docker compose -f docker-compose.staging.yml down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable oskar-staging
```

> Harbor must be started separately — it manages its own systemd unit or manual `docker compose up`.
> Do not add `harbor.service` to `Requires=` unless you've confirmed it has a systemd unit.

---

## Step 12 — Switch to LDAP Auth

Once Manal confirms the LDAPS service account is active:

1. Edit `/opt/oskar/.env.staging`:
   ```
   LDAP_SERVER=ldaps://srxglobal.local
   LDAP_BIND_DN=CN=oskar-svc,OU=ServiceAccounts,DC=srxglobal,DC=local
   LDAP_BIND_PW=<password>
   LDAP_BASE_DN=DC=srxglobal,DC=local
   LDAP_ENABLED=true
   ```
2. Restart the app container:
   ```bash
   cd /opt/oskar
   sudo docker compose -f docker-compose.staging.yml --env-file .env.staging up -d oskar-app
   ```
3. Test login with a real AD account.

---

## Upgrading to a New Version

On the VM:

```bash
# Get updated source
cd /opt/oskar-src/Oskar-master
git pull   # or re-download zip

# Rebuild and push
cd /opt/oskar-src/Oskar-master
docker build -t 10.131.1.10/oskar/oskar-app:v0.1.1 -f Dockerfile .
docker push 10.131.1.10/oskar/oskar-app:v0.1.1
docker build -t 10.131.1.10/oskar/oskar-frontend:v0.1.1 -f frontend/Dockerfile ./frontend
docker push 10.131.1.10/oskar/oskar-frontend:v0.1.1

# Update tag and restart
cd /opt/oskar
sed -i 's/TAG=v0.1.0/TAG=v0.1.1/' .env.staging
sudo docker compose -f docker-compose.staging.yml --env-file .env.staging pull
sudo docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
sudo docker exec -w /app oskar-app-staging alembic upgrade head
```

---

## Production Promotion

When staging is validated and LDAPS + Movex are confirmed:

1. Copy `.env.staging` → `.env.prod`, change:
   - `MOVEX_CONO=100`
   - `LDAP_ENABLED=true`
   - `OSKAR_ENV=production`
   - Generate fresh `JWT_SECRET_KEY_STAGING` and `POSTGRES_PASSWORD` for production
2. Run `docker-compose.yml` (production) on the same VM
3. Disable `DBCHK_OpenECN` SQL Server Agent job on DBSRV (G-6)
4. Announce go-live to Karen

---

## Troubleshooting

### T-01 — `docker login 10.131.1.10` fails: `connection refused (port 443)`

Docker is trying HTTPS. `/etc/docker/daemon.json` is missing or has not been applied.

```bash
cat /etc/docker/daemon.json   # verify insecure-registries present
sudo systemctl restart docker
docker info | grep -A5 "Insecure"
```

---

### T-02 — Harbor containers down after VM reboot

Harbor does not have a systemd unit by default. Start manually:

```bash
cd /opt/harbor && sudo docker compose up -d
```

Then retry `docker login`.

---

### T-03 — Frontend container restarts: `chown failed (Operation not permitted)`

The Dockerfile uses `nginx:alpine` (requires root for chown). Must use `nginxinc/nginx-unprivileged:alpine` instead, which runs as UID 101 and listens on port 8080.

Verify [frontend/Dockerfile](../../frontend/Dockerfile) line 16 reads:
```
FROM nginxinc/nginx-unprivileged:alpine AS runner
```

Rebuild and re-push the frontend image.

---

### T-04 — Worker unhealthy but logs show `celery ready`

No healthcheck is defined for Celery workers in the compose file. Docker reports `unhealthy`
by default when a healthcheck is present but failing, or `health: starting` briefly. If logs
show `celery@<id> ready` and tasks are registered, the worker is fine — ignore the status.

---

### T-05 — `npm ci` fails during frontend build: `package.json and package-lock.json out of sync`

The lock file needs regenerating. On the VM:

```bash
cd /opt/oskar-src/Oskar-master/frontend
npm install
```

Then retry `docker build`.

---

### T-06 — `alembic upgrade head` fails: `No config file 'alembic.ini' found`

The image was built from an old Dockerfile that only copied `src/`. Current Dockerfile includes:
```dockerfile
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY scripts/ ./scripts/
```

Rebuild the backend image and re-push.

---

### T-07 — `seed_demo.py` fails: `No such file or directory`

The container is `read_only: true` — `docker cp` and `mkdir` inside the container fail.
Use the one-off container approach from Step 8 (volume mount the scripts directory).

---

### T-08 — `docker compose up` warnings: `variable is not set`

Variables in `docker-compose.staging.yml` that aren't in `.env.staging` default to blank.
This is a warning, not an error. The stack will still start. Add missing variables to
`.env.staging` if the corresponding features are needed.

---

## Sprint 5 Acceptance Checklist

- [x] Harbor UI accessible at `http://10.131.1.10`
- [x] `docker login 10.131.1.10` succeeds from VM
- [x] `oskar-app:v0.1.0` and `oskar-frontend:v0.1.0` pushed to Harbor
- [x] All 5 staging containers Up (`oskar-app`, `oskar-worker`, `oskar-beat`, `oskar-frontend`, `oskar-db-staging`)
- [x] `alembic upgrade head` — 12 migrations applied cleanly
- [x] Seed data — 7 ECNs created across all workflow stages
- [x] `curl http://localhost:8001/health` returns `{"status":"ok"}`
- [ ] Login with demo credentials works from a browser on the LAN
- [ ] ECN list loads with ≥5 seed ECNs visible in browser
- [ ] ECN workflow transition completes in browser
- [ ] `oskar-staging.service` enabled in systemd
- [ ] IIS vhost `oskar.srxglobal.local` routes correctly to backend + frontend
- [ ] LDAP auth switchover (pending Manal LDAPS confirmation)
