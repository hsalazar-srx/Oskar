# Runbook — OSKAR VM Deployment
# Target: apac-plm-ops.srxglobal.local (Ubuntu 24.04 LTS, VMware)
# Owner: Lead Engineer (hsalazar)
# Last updated: 2026-05-28
#
# This runbook covers first deployment (staging) and production promotion.
# Harbor installation is a separate prerequisite: docs/runbooks/harbor-installation.md

---

## Overview

| Item | Value |
|------|-------|
| VM hostname | `apac-plm-ops.srxglobal.local` |
| VM specs | 4 CPUs / 16 GB RAM / 100 GB storage |
| Harbor registry | `apac-plm-ops.srxglobal.local` (same VM) |
| Staging backend port | `8001` |
| Staging frontend port | `3001` |
| Production backend port | `8000` |
| Production frontend port | `3000` |
| Compose files | `docker/docker-compose.staging.yml`, `docker/docker-compose.yml` |
| Secrets on VM | `/etc/oskar/secrets.env` (owner `root:oskar-app`, mode `0640`) |
| App directory on VM | `/opt/oskar` |
| MOVEX CONO | `300` = staging/UAT, `100` = production only |

---

## Prerequisites

Before running this runbook, confirm:

- [ ] Harbor installed and `oskar` project created — see `docs/runbooks/harbor-installation.md`
- [ ] DNS A record `apac-plm-ops.srxglobal.local` → VM IP added by Manal
- [ ] SSH access to VM as `hsalazar` (or another sudoer)
- [ ] Harbor `ca.crt` trusted on this dev machine (so `docker push` works) — see Harbor runbook §2
- [ ] `docker login apac-plm-ops.srxglobal.local` succeeds from this dev machine

---

## Step 1 — Build and Push Images

Run from the `c:\Projects\Oskar` directory on your dev machine:

```powershell
# Set credentials (use Harbor admin or a robot account)
$env:REGISTRY         = "apac-plm-ops.srxglobal.local/oskar"
$env:REGISTRY_USER    = "admin"
$env:REGISTRY_TOKEN   = "<harbor-password>"

# Build and push — tags as v0.1.0 AND latest
bash scripts/push-image.sh v0.1.0
```

Confirm both images appear in Harbor:
`https://apac-plm-ops.srxglobal.local` → Projects → oskar → Repositories

Expected:
- `apac-plm-ops.srxglobal.local/oskar/oskar-app:v0.1.0`
- `apac-plm-ops.srxglobal.local/oskar/oskar-frontend:v0.1.0`

---

## Step 2 — Create App Directory and Copy Files

SSH into the VM:

```bash
ssh hsalazar@apac-plm-ops.srxglobal.local
sudo mkdir -p /opt/oskar/docker /opt/oskar/scripts
sudo chown -R hsalazar:hsalazar /opt/oskar
```

From your dev machine, copy the compose file and scripts:

```powershell
$vm = "hsalazar@apac-plm-ops.srxglobal.local"
scp c:\Projects\Oskar\docker\docker-compose.staging.yml "${vm}:/opt/oskar/docker/"
scp c:\Projects\Oskar\docker\docker-compose.yml "${vm}:/opt/oskar/docker/"
scp c:\Projects\Oskar\scripts\setup-server-secrets.sh "${vm}:/opt/oskar/scripts/"
scp c:\Projects\Oskar\scripts\seed_demo.py "${vm}:/opt/oskar/scripts/"
scp c:\Projects\Oskar\scripts\seed-dev-data.sql "${vm}:/opt/oskar/scripts/"
```

---

## Step 3 — Provision Secrets

On the VM:

```bash
cd /opt/oskar
sudo bash scripts/setup-server-secrets.sh
```

The script prompts for each secret interactively. Values needed:

| Secret | Value |
|--------|-------|
| `OSKAR_DB_PASSWORD` | Strong password — generate: `openssl rand -base64 32 \| tr -d '/+=' \| cut -c1-24` |
| `JWT_SECRET_KEY` | 64-hex-char key: `openssl rand -hex 32` |
| `LDAP_BIND_PW` | Service account password (from Manal, or leave placeholder until LDAPS is confirmed) |
| `CELERY_SECURITY_KEY` | 64-hex-char key: `openssl rand -hex 32` |
| `SMTP_PASSWORD` | Leave blank — 10.10.0.155 relay is unauthenticated |
| `AUDIT_CHECKPOINT_RECIPIENT` | e.g. `it_staff@srxglobal.com` |

Record the SHA-256 checksum printed at the end in `ai/evidence/decision-log.md`.

---

## Step 4 — Create the Staging Environment File

On the VM, create `/opt/oskar/.env.staging`:

```bash
sudo tee /opt/oskar/.env.staging <<'EOF'
# OSKAR Staging — apac-plm-ops.srxglobal.local
# MOVEX CONO=300 (dev/UAT) — NEVER use 300 in production

REGISTRY=apac-plm-ops.srxglobal.local/oskar
TAG=v0.1.0

POSTGRES_PASSWORD=<from-secrets.env>

# Auth — start with dev bypass; switch to ldap once Manal confirms LDAPS
AUTH_PROVIDER=dev
DEV_USERS=hsalazar,eng_user,qm_user,dc_user

# When switching to LDAP (S5-10):
# AUTH_PROVIDER=ldap
# LDAP_SERVER=ldaps://srxglobal.local
# LDAP_PORT=636
# LDAP_BIND_DN=CN=oskar-svc,OU=ServiceAccounts,DC=srxglobal,DC=local
# LDAP_BIND_PW=<from-secrets.env>
# LDAP_BASE_DN=DC=srxglobal,DC=local

JWT_SECRET_KEY=<from-secrets.env>
JWT_SECRET_KEY_STAGING=<from-secrets.env>
REFRESH_TOKEN_SECRET_STAGING=<same-as-jwt-or-generate-separate>

CELERY_SECURITY_KEY=<from-secrets.env>

MOVEX_API_URL=http://srxwebapp1.srxglobal.local/api
MOVEX_API_KEY=<movex-api-key>
MOVEX_CONO=300

SMTP_HOST=10.10.0.155
SMTP_PORT=25
SMTP_SENDER=oskar-noreply@srxglobal.local

VITE_API_URL=/api/v1
EOF
sudo chmod 0640 /opt/oskar/.env.staging
sudo chown root:oskar-app /opt/oskar/.env.staging 2>/dev/null || true
```

> Fill in the `<...>` values from `/etc/oskar/secrets.env` and your MOVEX API key.

---

## Step 5 — Log In to Harbor from VM

```bash
docker login apac-plm-ops.srxglobal.local
# Username: admin (or robot account)
# Password: <harbor-password>
```

If DNS doesn't resolve yet, add a temporary hosts entry:

```bash
echo "$(hostname -I | awk '{print $1}')  apac-plm-ops.srxglobal.local" | sudo tee -a /etc/hosts
```

---

## Step 6 — Start Staging Stack

```bash
cd /opt/oskar
docker compose \
  -f docker/docker-compose.staging.yml \
  --env-file .env.staging \
  pull

docker compose \
  -f docker/docker-compose.staging.yml \
  --env-file .env.staging \
  up -d
```

Verify all containers are up:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected:
```
oskar-app-staging      Up (healthy)   0.0.0.0:8001->8000/tcp
oskar-worker-staging   Up             
oskar-frontend-staging Up             0.0.0.0:3001->80/tcp
oskar-db-staging       Up (healthy)   0.0.0.0:5433->5432/tcp
```

---

## Step 7 — Run Migrations

```bash
docker exec oskar-app-staging \
  alembic -c alembic.ini upgrade head
```

Expected: Alembic prints each migration in sequence up to the latest revision. No errors.

> **Note:** The `alembic.ini` and `alembic/` directory are not in the container image.
> If this fails, copy them first or run migrations from a one-off container:

```bash
docker run --rm \
  --network oskar-staging-network \
  --env DATABASE_URL=postgresql+asyncpg://oskar:<password>@oskar-db-staging:5432/oskar_staging \
  apac-plm-ops.srxglobal.local/oskar/oskar-app:v0.1.0 \
  alembic upgrade head
```

---

## Step 8 — Seed Demo Data

```bash
docker exec oskar-app-staging \
  python scripts/seed_demo.py
```

Expected: prints created ECN IDs for each workflow stage (Draft, Engineering Review, etc.).

---

## Step 9 — Smoke Test

```bash
# Health
curl http://localhost:8001/health
# Expected: {"status":"ok"}

# Login (dev auth bypass)
curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"hsalazar","password":"password"}' | python3 -m json.tool

# ECN list (use token from login response)
TOKEN="<access_token_from_above>"
curl -s http://localhost:8001/api/v1/ecn/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Also verify the frontend:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/
# Expected: 200
```

---

## Step 10 — IIS Reverse Proxy (SRXWEBAPP1)

Create a new IIS site or virtual application on SRXWEBAPP1 pointing to:

| Item | Value |
|------|-------|
| Hostname | `oskar.srxglobal.local` |
| Backend proxy | `http://apac-plm-ops.srxglobal.local:8001` (FastAPI) |
| Frontend proxy | `http://apac-plm-ops.srxglobal.local:3001` (nginx) |

Route `/api/*` to the backend, all other requests to the frontend. Use the same pattern as SM-Portal (ADR-022 / `UsePathBase`).

---

## Step 11 — Enable Auto-Start on Reboot

```bash
sudo tee /etc/systemd/system/oskar-staging.service <<'EOF'
[Unit]
Description=OSKAR Staging Stack
Requires=docker.service harbor.service
After=docker.service harbor.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/oskar
EnvironmentFile=/opt/oskar/.env.staging
ExecStart=/usr/bin/docker compose -f docker/docker-compose.staging.yml up -d
ExecStop=/usr/bin/docker compose -f docker/docker-compose.staging.yml down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable oskar-staging
```

---

## Step 12 — Switch to LDAP Auth (S5-10)

Once Manal confirms the LDAPS service account (`CN=oskar-svc,...`) is active:

1. Edit `/opt/oskar/.env.staging` — uncomment `AUTH_PROVIDER=ldap` block, comment out `AUTH_PROVIDER=dev`
2. Restart the app container:
   ```bash
   docker compose -f docker/docker-compose.staging.yml --env-file .env.staging up -d oskar-app
   ```
3. Test login with a real AD account.

---

## Upgrading to a New Version

```powershell
# On dev machine — build and push new tag
bash scripts/push-image.sh v0.1.1
```

```bash
# On VM — pull and restart
cd /opt/oskar
sed -i 's/TAG=v0.1.0/TAG=v0.1.1/' .env.staging
docker compose -f docker/docker-compose.staging.yml --env-file .env.staging pull
docker compose -f docker/docker-compose.staging.yml --env-file .env.staging up -d
docker exec oskar-app-staging alembic upgrade head
```

---

## Production Promotion

When staging is validated and LDAPS + Movex are confirmed:

1. Copy `.env.staging` → `.env.prod`, change:
   - `MOVEX_CONO=100`
   - `AUTH_PROVIDER=ldap`
   - `OSKAR_ENV=production`
   - Generate fresh `JWT_SECRET_KEY` and `POSTGRES_PASSWORD` for production
2. Run `docker-compose.yml` (production) on the same VM or a dedicated host
3. Disable `DBCHK_OpenECN` SQL Server Agent job on DBSRV (G-6)
4. Announce go-live to Karen

---

## Troubleshooting

### T-01 — `alembic upgrade head` fails: `relation "alembic_version" does not exist`

The database exists but migrations have never been run. This is normal on first deploy — Alembic will create the table and run all migrations. Only fails if the DB is missing entirely.

**Check the DB is up:**
```bash
docker exec oskar-db-staging pg_isready -U oskar -d oskar_staging
```

---

### T-02 — Container exits immediately: `exec /app/entrypoint.sh: no such file or directory`

The image was built without the `alembic/` or `scripts/` directory. The `Dockerfile` only copies `src/`. Run migrations via one-off container (see Step 7 fallback).

---

### T-03 — `docker pull` fails: `unauthorized`

Either the Harbor password is wrong or the session expired. Re-run `docker login apac-plm-ops.srxglobal.local`.

---

### T-04 — `curl http://localhost:8001/health` returns connection refused

The `oskar-app-staging` container is not running or not healthy. Check:
```bash
docker logs oskar-app-staging --tail 50
docker inspect oskar-app-staging | grep -A5 Health
```

Common causes:
- DB not yet healthy when app started — wait 30s and `docker compose up -d` again
- Missing env var — check `.env.staging` for blank required values

---

### T-05 — Celery worker exits: `KeyError: 'CELERY_SECURITY_KEY'`

The `CELERY_SECURITY_KEY` env var is not set in the container. Verify it is present in `.env.staging` and passed to the worker service in `docker-compose.staging.yml`.

---

## Sprint 5 Acceptance Checklist

- [ ] `https://apac-plm-ops.srxglobal.local` (Harbor UI) returns 200
- [ ] `curl http://localhost:8001/health` returns `{"status":"ok"}`
- [ ] Login with demo credentials works from a browser on the LAN
- [ ] ECN list loads with ≥5 seed ECNs visible
- [ ] ECN workflow transition (Submit → Engineering Review) completes
- [ ] Email digest fires to test inbox (SMTP smoke)
- [ ] `docker ps` shows `oskar-worker-staging` and `oskar-beat-staging` both `Up`
- [ ] `oskar-staging.service` enabled in systemd
- [ ] IIS vhost `oskar.srxglobal.local` routes correctly to backend + frontend
