# OSKAR — Lessons Learned

Newest first. Full details in the Knowledge Management vault.

---

### [2026-08-12] "Matches Stargile" design claim (D6) was never verified against Stargile's source
**Type:** process gap | **Severity:** medium
ADR-012's D6 stated "BOM apply follows Stargile supersession: CHANGE = close old line (TDAT = new FDAT − 1)" with zero source citation — the only uncited claim among 7 sibling decisions (D4/D5 cite exact tables + verification dates). Implemented, tested, live-tested (2026-08-11) before a movex-rest-api-side bug (TDAT doesn't persist) triggered a fresh look. Checking the suggested workaround against Stargile's actual source (`ProcessBOMLineRule.java`) found Stargile never used UpdateComponent/TDAT for BOM lines at all — the real pattern is Delete+AddComponent, which is what got implemented as I2-19. Rule going forward: any "matches legacy system" claim needs a file path + line number or verification date, same bar as any other technical claim.
Full detail: `ai/evidence/lesson-learned-LL-003.md`.
See vault: `vault/learnings/oskar/2026-08-12-matches-stargile-claim-unverified-d6.md`

### [2026-06-17] nginx `proxy_pass` variable syntax causes silent 404 in Docker staging
**Type:** pitfall | **Severity:** high
Using `set $backend` variable in `proxy_pass` causes nginx to return 404 silently when Docker DNS resolution fails at request time — even when `nslookup` works. Use a literal hostname instead. Diagnosed by watching backend logs while hitting via nginx: no log line = nginx owns the 404.
See vault: `vault/learnings/oskar/2026-06-17-nginx-proxy-pass-variable-silent-404.md`
