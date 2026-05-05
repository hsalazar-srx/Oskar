# PRE-10 — Container Image Registry

**Status:** Accepted — Provisioning in progress
**Date:** 2026-04-08
**Owner:** Manal (Infrastructure Manager)
**Type:** Operational

---

## Decision

Harbor (self-hosted, open source) installed on the OSKAR Linux VM by Manal.
Azure CR and GitHub CR are not needed.

## Status

Manal provisioning Harbor on the OSKAR VM alongside the Linux deployment.
Expected: both VM and Harbor ready by 2026-04-17.

## Pending Action

Update `scripts/push-image.sh` REGISTRY variable to the Harbor hostname once Manal
provides it (e.g. `apac-plm-ops.srxglobal.local:5000` or a named vhost).

## Consequences

- Harbor web UI for image management — Manal owns it as infrastructure
- Image tags follow: `harbor-host/oskar/oskar-app:{git-sha}` and `:latest`
- `push-image.sh` must authenticate to Harbor using a service account (credentials via `.env`)
