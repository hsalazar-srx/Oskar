# OSKAR — Decision Log

> Lightweight chronological index. One line per decision.
> Full rationale lives in `decisions/` (pre-decisions, ADRs, implementation choices).
> Add an entry here whenever a decision is made — point to its file.

---

## Format

```
YYYY-MM-DD | SHORT DESCRIPTION | decisions/filename.md
```

---

## Log

2026-04-08 | LLM provider agnosticism: ai/ neutral, .providers/ swappable | [PRE-1](../../decisions/PRE-1-llm-provider-agnosticism.md)
2026-04-08 | Redis 3-DB logical separation (DB0 broker, DB1 cache, DB2 stream) | [PRE-2](../../decisions/PRE-2-redis-logical-separation.md)
2026-04-08 | IdentityProvider Protocol: LDAP production, EntraID stub | [PRE-3](../../decisions/PRE-3-identity-provider-interface.md)
2026-04-08 | All API routes versioned /api/v1/ from Sprint 1 Day 1 | [PRE-4](../../decisions/PRE-4-api-versioning.md)
2026-04-08 | SupplierAdapter ABC: 1 real + 5 stubs, per-adapter circuit breaker | [PRE-5](../../decisions/PRE-5-supplier-adapter-abc.md)
2026-04-08 | Frontend standalone on own IIS vhost; SM-Portal nav tile link only | [PRE-6](../../decisions/PRE-6-frontend-deployment-model.md)
2026-04-08 | SM-Portal → OSKAR: link tile, no auth coupling | [ADR-001](../../decisions/ADR-001-sm-portal-oskar-navigation-link-no-auth-coupling.md)
2026-04-08 | Backup: pg_dump daily → D:\Backups\oskar\; RTO 4h RPO 24h | [PRE-7](../../decisions/PRE-7-backup-and-dr.md)
2026-04-08 | Staging: second Compose stack, ports 8001/5433/6380 | [PRE-8](../../decisions/PRE-8-staging-environment.md)
2026-04-08 | Notifications: SMTP primary; Teams stub; config deferred | [PRE-9](../../decisions/PRE-9-notification-mechanism.md)
2026-04-08 | Container registry: Harbor on OSKAR VM (Manal, by 2026-04-17) | [PRE-10](../../decisions/PRE-10-container-registry.md)
2026-04-08 | IFS out of scope for OSKAR v1; IFSAdapter = stub only (Karen confirmed) | no file — see ai/memory/01-manufacturing-context.md
2026-04-08 | Cutover: ECN-level boundary, 2-week drain period, hard cutover | no file — see ai/memory/05-stargile-ecn-reference.md Section 6
2026-04-09 | Decisions governance: decisions/ for all decisions; evidence/decision-log.md as index | this file
2026-04-09 | Dropped ai/04-pre-decisions.md — content migrated to decisions/PRE-1 through PRE-10 | —
2026-04-10 | Expert review: @architect + @security + @ecn-domain — validated Stargile analysis against OSKAR plan | ai/tasks/sprint-backlog.md updated
2026-04-10 | Workflow engine: Celery + PostgreSQL + transitions library; Transactional Outbox replaces LogicalUnitOfWork | [ADR-002](../../decisions/ADR-002-workflow-engine-celery-postgresql-transitions.md)
2026-04-10 | RBAC: AD groups (coarse) + PostgreSQL per-ECN assignments (fine); 11 active roles; retire MG/HR | [ADR-003](../../decisions/ADR-003-rbac-hybrid-ad-postgresql.md)
2026-04-10 | Audit chain: SHA-256 PostgreSQL append-only + daily checkpoint to Azure Blob; pg_audit enabled | [ADR-004](../../decisions/ADR-004-audit-chain-sha256-postgresql.md)
2026-04-10 | ERP write gate: state machine + single-use HMAC write_authorization_token + Celery task signing | [ADR-005](../../decisions/ADR-005-erp-write-gate.md)
2026-04-10 | Auth: LDAPS 636 (not 389); JWT 60min access + 8h HttpOnly refresh cookie; JTI blocklist | [ADR-006](../../decisions/ADR-006-authentication-ldaps-jwt-refresh.md)
2026-04-10 | ECN statuses: 12 (collapse Stargile 50+60 → APPROVED+IMPLEMENTED; ARCHIVED = logical flag) | ADR-002
2026-04-10 | MMS025MI.AddAlias + MPDDOC drawing creation confirmed missing from movex-rest-api — Sprint 2 blockers | Track A open item
2026-04-13 | Secrets management: server-side /etc/oskar/secrets.env + setup script; .env for dev; upgrade path to vault (PRE-11) | [PRE-11](../../decisions/PRE-11-secrets-management.md)
2026-04-13 | Observability: structlog JSON, correlation ID middleware, /health/live + /ready — Phase 0, not Phase 3 | ai/memory/11-observability.md
2026-04-13 | VM redundancy: single VM accepted for v1; manual fallback defined; standby VM deferred to Phase 2 | ai/memory/09-known-risks-and-pitfalls.md §8 (R-14)
2026-04-13 | Stargile source analysis validated complete for Sprint 1+2 scope; 3 open items correctly deferred post-POC | ai/memory/05-stargile-ecn-reference.md §8
2026-04-14 | IQ/OQ/PQ approval chain confirmed: IQ author=Manal, OQ/PQ author=Mihai, Approver=hsalazar, QM=Divya | ai/memory/07-compliance-requirements.md §3
2026-04-14 | P0-3 complete: scripts/setup-server-secrets.sh + .env.example (PRE-11 implementation) | decisions/PRE-11-secrets-management.md
2026-04-14 | P0-4 complete: structlog + CorrelationIdMiddleware + /health/live + /health/ready | ai/memory/11-observability.md
2026-04-14 | F-7 complete: transitions==0.9.2 added to requirements.txt | requirements.txt
2026-04-14 | DBCHK_OpenECN SQL Server job added to scope — OSKAR replaces with Open ECN list + Celery digest | ai/memory/05 §9, ai/memory/06 §13, sprint-backlog G-1 through G-6
2026-04-15 | OpenBao vault: feasibility confirmed (on-prem, single container, zero app code change); deferred to Phase 2 post-go-live to avoid Sprint 1 critical-path risk; PRE-11 file-based approach remains for v1; supersede PRE-11 with ADR-007 in Phase 2 | decisions/PRE-11-secrets-management.md + ai/memory/09-known-risks-and-pitfalls.md (R-13)
2026-04-15 | CONO=300 (dev/staging), CONO=100 (prod); MOVEX_CONO env var — never hardcoded; all dev/staging use 300 | [PRE-12](../../decisions/PRE-12-movex-company-environment-mapping.md)
2026-04-17 | Redis eliminated from production stack; Celery broker → celery[sqlalchemy] PostgreSQL transport; JTI blocklist + refresh tokens → PostgreSQL tables; event stream → HTTP polling; supersedes PRE-2 | [ADR-007](../../decisions/ADR-007-redis-elimination-postgresql-broker.md)
