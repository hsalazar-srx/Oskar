# OSKAR — Lessons Learned

Newest first. Full details in the Knowledge Management vault.

---

### [2026-06-17] nginx `proxy_pass` variable syntax causes silent 404 in Docker staging
**Type:** pitfall | **Severity:** high
Using `set $backend` variable in `proxy_pass` causes nginx to return 404 silently when Docker DNS resolution fails at request time — even when `nslookup` works. Use a literal hostname instead. Diagnosed by watching backend logs while hitting via nginx: no log line = nginx owns the 404.
See vault: `vault/learnings/oskar/2026-06-17-nginx-proxy-pass-variable-silent-404.md`
