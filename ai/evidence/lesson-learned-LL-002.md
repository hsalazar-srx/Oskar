# Lesson Learned — LL-002
# Sprint 5 VM Deployment — Docker Registry Access Blocked by Corporate Proxy

**Date identified:** 2026-06-02
**Sprint:** Sprint 5 (VM deployment)
**Identified by:** Lead Engineer (hector.salazar@srxglobal.com)
**Severity:** Medium — blocked the planned deployment path for ~3 hours
**Resolution:** Build images on the VM directly; bypass proxy entirely
**Status:** Resolved

---

## What Happened

Sprint 5 planned to build Docker images on Windows and push them to the Harbor registry on
`apac-plm-ops.srxglobal.local` (`10.131.1.10`). This is the standard workflow: dev machine
builds, pushes to registry, VM pulls.

The push never worked. Every `docker login` or `docker push` attempt from Windows returned
either a TLS error, a 503, or a corporate proxy block page. The root cause was a transparent
corporate proxy that intercepts all HTTP/HTTPS traffic to RFC 1918 addresses
(`private-ip-addresses` category). The proxy cannot be bypassed from the Windows side —
`$env:NO_PROXY`, `$env:HTTPS_PROXY = $null`, and per-registry insecure config in Rancher
Desktop's `daemon.json` were all ineffective because the proxy operates at the network layer,
not the application layer.

---

## Timeline

| Time | Event |
|------|-------|
| Session start | `docker login 10.131.1.10` → EOF error |
| +30 min | Identified: Rancher Desktop uses WSL, not Windows Docker → cert directory ineffective |
| +45 min | Patched `/etc/docker/daemon.json` in WSL with `insecure-registries` |
| +60 min | Login switched from EOF → TLS handshake reset → identified: Harbor cert missing IP SAN |
| +90 min | Regenerated cert with `IP.1=10.131.1.10` in `v3.ext` |
| +100 min | New error: 308 redirect (HTTPS still enabled in `harbor.yml`) |
| +120 min | Disabled HTTPS in Harbor, re-ran `./prepare`, restarted — 503 persists |
| +150 min | `curl` from Windows → 503 with corporate proxy HTML block page |
| +165 min | Confirmed: transparent proxy blocks all `private-ip-addresses` category — cannot bypass |
| +180 min | Decision: build on VM, push to Harbor from VM (no proxy on VM) |
| +185 min | SSH was not installed on VM — installed `openssh-server` |
| +190 min | Downloaded source zip from GitHub directly on VM — bypasses SCP/proxy problem |
| +200 min | `docker login 10.131.1.10` from VM → succeeds immediately |

---

## Root Cause Analysis

### Primary cause — Transparent proxy at network layer

The corporate proxy uses category-based filtering. The `private-ip-addresses` category blocks
all connections to RFC 1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).

This is a network-layer intercept — the proxy terminates the TCP connection before the
application sees it. No application-layer workaround (env vars, daemon config, `--insecure`)
can bypass it. The proxy generates its own HTML block page in the response body.

### Secondary cause — Rancher Desktop's ephemeral daemon.json

Rancher Desktop (used instead of Docker Desktop on this machine) manages
`/etc/docker/daemon.json` inside its WSL distro and rewrites it on every restart. The
provisioning script approach (`%APPDATA%\rancher-desktop\provisioning\*.start`) was attempted
but proved unreliable — the script runs before dockerd stabilises and the file gets overwritten.

This meant that even if the proxy was not in play, the `insecure-registries` config had to be
manually re-applied after every Rancher Desktop restart.

### Contributing factor — Harbor TLS cert missing IP SAN

The initial Harbor TLS cert was generated with only `CN=apac-plm-ops.srxglobal.local`. Docker
(correctly) rejects certs that lack a Subject Alternative Name matching the address used to
connect. When connecting by IP (`10.131.1.10`), the cert needed `IP.1=10.131.1.10` in the SAN.

This was fixed, but was a separate 30-minute detour before the proxy issue was identified.

### Contributing factor — Harbor admin account locked

Multiple failed login attempts during debugging locked the Harbor `admin` account. The lock
is stored in PostgreSQL (`harbor_user` table) and does not self-expire. Resolution required a
full Harbor stack reset (`docker compose down -v`, wipe `/data/harbor/*`, re-run `./prepare`).

---

## Impact Assessment

**Actual impact:** ~3 hours additional deployment time in Sprint 5. No data loss. No production
impact (staging environment only).

**If undetected until production deployment:** Production deployment would face the same proxy
block. The VM-side build approach is the correct permanent workaround for this network topology.

---

## What Was Done Well

- The decision to switch to "build on VM" was made quickly once the proxy block was confirmed —
  further debugging of the Windows-side proxy bypass would have been wasted time.
- Harbor HTTP-only mode (disabling TLS) was correctly identified as the right tradeoff for an
  internal-only registry — avoids cert management complexity with no security loss on a LAN.
- The `docker login` from the VM worked on the first attempt after the insecure registry config
  was applied — confirming the proxy was the Windows-only problem.

---

## Resolution

**Deployment path changed:** Images are built on the VM and pushed to Harbor from the VM.
Windows is used only for development. The push-from-dev-machine workflow documented in the
original runbook is not viable in this network topology.

**Updated runbook:** `docs/runbooks/vm-deployment.md` now documents the VM-side build approach
as the primary path. The Windows push approach has been removed.

---

## Subsidiary Issues Fixed During Sprint 5

The following bugs were found and fixed during the deployment attempt:

| # | Issue | Fix |
|---|-------|-----|
| 1 | Frontend build: `npm ci` fails — lock file out of sync | Run `npm install` on VM before `docker build` |
| 2 | Frontend container crashes: nginx `chown` fails with `read_only: true` | Switch to `nginxinc/nginx-unprivileged:alpine` (port 8080) |
| 3 | `nginx:alpine-unprivileged` tag doesn't exist | Correct image: `nginxinc/nginx-unprivileged:alpine` |
| 4 | `alembic upgrade head` fails: `alembic.ini` not found | Add `COPY alembic/ ./alembic/` and `COPY alembic.ini .` to `Dockerfile` |
| 5 | `seed_demo.py` fails: can't write to container filesystem | Run seed via one-off container with source volume-mounted |
| 6 | `docker compose up oskar-beat` fails: service not found | VM had old compose file — `cp` from source replaces it |
| 7 | `oskar-worker` reports unhealthy | No healthcheck defined for Celery — expected, not a real failure |

---

## Process Changes Adopted

1. **VM-side build is now the standard deployment path.** Do not attempt to push from Windows
   to any VM on the `10.x.x.x` range — the proxy will block it.

2. **SSH must be installed on VMs before deployment.** Add `openssh-server` to the VM
   provisioning checklist. `scp` and remote builds both require it.

3. **Harbor runs HTTP-only.** No TLS cert management required for the internal registry.
   `insecure-registries` must be set on any Docker host that pushes to or pulls from it.

4. **`Dockerfile` must include `alembic/`, `alembic.ini`, and `scripts/`.** These were missing
   from the initial image — migrations and seed data both failed without them.

5. **Frontend must use `nginxinc/nginx-unprivileged:alpine`.** The standard `nginx:alpine` image
   requires root to `chown` its cache directories, which conflicts with `read_only: true` +
   `cap_drop: ALL` in the compose security hardening.

---

## References

- `docs/runbooks/vm-deployment.md` — updated deployment runbook
- `Dockerfile` — now includes `alembic/`, `alembic.ini`, `scripts/`
- `frontend/Dockerfile` — now uses `nginxinc/nginx-unprivileged:alpine`
- `docker/docker-compose.staging.yml` — frontend port changed to `3001:8080`
