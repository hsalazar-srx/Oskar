# Skill: /oskar-commit-template
**Tier:** 1 — Developer workflow
**MAS skill:** `knowledge/commit-miner`

## Purpose
Generate a correctly-formatted Conventional Commits message for any OSKAR change.
Applies the MAS commit-miner convention scoped to OSKAR scopes and types.

## Format
```
<type>(oskar-<scope>): <imperative description>

[optional body — what and why, not how]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

## Types
| Type | Use for |
|------|---------|
| `feat` | New feature or endpoint |
| `fix` | Bug fix |
| `docs` | Documentation, `ai/` file updates, ADRs |
| `refactor` | Code restructuring, no behaviour change |
| `chore` | Build, config, Docker, scripts |
| `test` | Test additions or changes |
| `adr` | Architecture Decision Record |

## Scopes
| Scope | Use for |
|-------|---------|
| `ecn` | ECN module (Iteration 1) |
| `bom` | BOM module (Iteration 2) |
| `supplier` | Supplier Intelligence (Iteration 3) |
| `auth` | IdentityProvider, JWT, LDAP |
| `api` | FastAPI routing, versioning, middleware |
| `db` | PostgreSQL schema, migrations, models |
| `docker` | Docker Compose files |
| `ai` | `ai/` context files |
| `harness` | Phase 0 harness, `.providers/`, scripts |
| `audit` | SHA-256 audit chain |

## Examples
```
feat(oskar-ecn): add ECN approval workflow endpoint /api/v1/ecn/{id}/approve
fix(oskar-auth): correct LDAP group membership query for nested AD groups
chore(oskar-docker): remove oskar-redis container — switch to PostgreSQL broker (ADR-007)
docs(oskar-ai): update 03-oskar-architecture.md with Linux VM deployment decision
adr(oskar-auth): ADR-001 IdentityProvider protocol + LDAPIdentityProvider
test(oskar-ecn): add approval chain unit tests for multi-approver scenario
refactor(oskar-api): apply /api/v1/ prefix to all remaining unversioned routes
```

## Invoke
When asked to generate a commit message: ask for the change summary if not provided,
then apply this format. Include `Co-Authored-By` on all AI-assisted commits.
