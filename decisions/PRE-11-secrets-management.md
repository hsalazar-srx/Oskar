# PRE-11 — Secrets Management: Server-Side Secrets File (OSKAR Linux VM)

**Date:** 2026-04-13
**Status:** Accepted
**Deciders:** Lead Engineer
**Context:** Phase 0 — must be in place before any credential is stored or Sprint 1 begins.

---

## Context

OSKAR requires several runtime secrets before Sprint 1 code can run:

| Secret | Used by |
|--------|---------|
| `OSKAR_DB_PASSWORD` | oskar-app, oskar-worker → PostgreSQL 16 |
| `JWT_SECRET_KEY` | oskar-app — JWT signing (≥256-bit random) |
| `REDIS_PASSWORD` | oskar-app, oskar-worker, Celery → Redis 7 |
| `LDAP_BIND_PW` | oskar-app → Active Directory (LDAPS bind) |
| `CELERY_SECURITY_KEY` | oskar-worker → Celery task signing |
| `SMTP_PASSWORD` | oskar-worker → corporate SMTP relay (Sprint 2) |

The problem: OSKAR runs on an on-prem Linux VM with no Azure Key Vault, no HashiCorp Vault, no rotation infrastructure. The naive approach — commit secrets to `.env` or `docker-compose.yml` — is a DISP Tier 1 finding and a `gitleaks` blocker.

---

## Decision

Adopt the **SM-Portal server-side secrets file pattern**, adapted for Linux + Docker.

### Development (local workstation)

All secrets live in a `.env` file in the project root:
- `.env` is in `.gitignore` — never committed
- `.env.example` is committed with placeholder values only
- `gitleaks` pre-commit hook blocks any commit containing real secret values
- Developer runs: `cp .env.example .env` then fills in dev values

### Production (OSKAR Linux VM)

Secrets are stored in `/etc/oskar/secrets.env` — **outside the deployment directory**:

```
/etc/oskar/secrets.env
```

File is:
- Owned by `root`, group `oskar-app` (the Linux service user inside the container maps to this)
- Permissions: `0640` — root can write, oskar-app can read, world cannot
- Mounted read-only into all Docker containers that need it:

```yaml
# docker-compose.prod.yml (relevant excerpt)
services:
  oskar-app:
    env_file:
      - /etc/oskar/secrets.env
  oskar-worker:
    env_file:
      - /etc/oskar/secrets.env
```

**The secrets file is never inside the repo, never inside the Docker image, never in a volume that is backed up to shared storage.**

### Provisioning

A setup script `scripts/setup-server-secrets.sh` is committed to the repo. It:
1. Creates `/etc/oskar/` directory if absent
2. Writes `/etc/oskar/secrets.env` from interactive prompts (never from args — no shell history)
3. Sets ownership `root:oskar-app` and mode `0640`
4. Prints a confirmation checksum — Lead Engineer records this in `ai/evidence/decision-log.md`

Running this script is a **Sprint 1 pre-condition**. Manal runs it on the OSKAR VM before the first `docker compose up -d`.

### Upgrade path

When Azure Key Vault or HashiCorp Vault is provisioned (Phase 2+), the Docker `env_file` block is replaced with a secrets-fetching sidecar or startup hook — **no application code changes required**, because the app already reads from environment variables.

---

## Rejected alternatives

| Alternative | Reason rejected |
|------------|----------------|
| Docker secrets (swarm) | Requires Docker Swarm; OSKAR uses Compose only |
| Hardcoded in `docker-compose.yml` | DISP Tier 1 finding; `gitleaks` blocks commit |
| `.env` file on VM inside repo clone | Survives `git pull --force`; accidental commit risk |
| Azure Key Vault now | No Azure subscription confirmed for on-prem VM access |

---

## Consequences

- **Positive:** No secrets in git history, ever. `gitleaks` scan is clean. DISP-compliant.
- **Positive:** Same pattern as SM-Portal (team familiar with it). Upgrade path to vault is clear.
- **Negative:** Manual provisioning step required on every new VM. Mitigated by setup script.
- **Negative:** No rotation policy. Accepted for v1 — rotation is out of scope. Documented as R-13.

---

## Implementation checklist (Phase 0)

- [ ] Create `scripts/setup-server-secrets.sh`
- [ ] Create `.env.example` with all secret key names and placeholder values
- [ ] Verify `.env` and `secrets.env` are in `.gitignore`
- [ ] Install `gitleaks` pre-commit hook (already in Sprint 1 pre-conditions)
- [ ] Add `env_file: /etc/oskar/secrets.env` to `docker-compose.prod.yml` (Sprint 1)
- [ ] Manal runs setup script on OSKAR VM before first deploy
