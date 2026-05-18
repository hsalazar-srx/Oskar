-- OSKAR — Local Development Seed Data
-- Run after: docker compose exec oskar-app alembic upgrade head
--
-- Usage:
--   docker compose -f docker/docker-compose.dev.yml exec oskar-db-dev \
--     psql -U oskar -d oskar -f /dev/stdin < scripts/seed-dev-data.sql
--
-- Or via psql directly (if port 5432 is exposed to host):
--   psql postgresql://oskar:oskar_dev@localhost:5432/oskar -f scripts/seed-dev-data.sql
--
-- This seeds:
--   - system_role_users: one user per role for facility 'L' (Melbourne)
--   - All usernames match DEV_USERS in .env so the dev auth bypass accepts them
--
-- Idempotent: ON CONFLICT DO NOTHING — safe to run multiple times.

-- ── DC: Document Controller ────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('L', 'DC', 'hsalazar', 'Hector Salazar', 'hsalazar@srxglobal.local', TRUE, 'seed-dev-data.sql', 'Lead Engineer / DC for local dev')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── OR: Originator (any engineer can be OR — seeding one for testing) ──────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('L', 'OR', 'eng_user', 'Engineering User', 'eng_user@srxglobal.local', TRUE, 'seed-dev-data.sql', 'Test originator for local dev')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── SE: Senior Engineer ────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('L', 'SE', 'testuser', 'Test User', 'testuser@srxglobal.local', TRUE, 'seed-dev-data.sql', 'Test SE for local dev')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── EM: Engineering Manager ────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('L', 'EM', 'dc_user', 'DC User', 'dc_user@srxglobal.local', TRUE, 'seed-dev-data.sql', 'Test EM for local dev')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── QM: Quality Manager ────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('L', 'QM', 'testuser', 'Test User', 'testuser@srxglobal.local', TRUE, 'seed-dev-data.sql', 'Test QM for local dev')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── PM: Production Manager ─────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('L', 'PM', 'testuser', 'Test User', 'testuser@srxglobal.local', TRUE, 'seed-dev-data.sql', 'Test PM for local dev')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── SC: Supply Chain ───────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('L', 'SC', 'testuser', 'Test User', 'testuser@srxglobal.local', TRUE, 'seed-dev-data.sql', 'Test SC for local dev')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── AD: Admin ─────────────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('L', 'AD', 'hsalazar', 'Hector Salazar', 'hsalazar@srxglobal.local', TRUE, 'seed-dev-data.sql', 'Admin for local dev')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- Verify
SELECT facility, role_id, username, display_name, is_active
FROM system_role_users
ORDER BY role_id, username;
