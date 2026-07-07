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
--   - system_role_users: 3 users per role for facility 'D' (Melbourne)
--   - All usernames must be in DEV_USERS in .env so the dev auth bypass accepts them
--
-- Idempotent: ON CONFLICT DO NOTHING — safe to run multiple times.
--
-- Role reference:
--   DC  Document Controller   — coordinates all gates; mandatory on every ECN
--   OR  Originator            — ECN creator; any engineer can hold this role per ECN
--   SE  Senior Engineer       — technical review at Engineering Review stage
--   CE  Chief Engineer        — escalation co-reviewer alongside SE
--   EM  Engineering Manager   — mandatory Management Review approver
--   QM  Quality Manager       — mandatory Management Review approver (ISO 13485)
--   PM  Production Manager    — conditional: required when routing_changes or operation_changes
--   SC  Supply Chain          — conditional: required when new_parts or lead_time_changes
--   FN  Finance               — conditional: required when wapc_delta_pct exceeds threshold
--   CA  Cost Accountant       — cost observer; no veto authority
--   AD  Administrator         — platform admin; place-on-hold and override only
--   RD  R&D / Product Eng.    — observer; notified when product family is affected
--   TE  Test Engineering      — observer; notified when change_to_documents=TRUE
--   MQ  Manufacturing Quality — observer; notified when ECN reaches CLOSED

-- ── DC: Document Controller ────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'DC', 'hsalazar',   'Hector Salazar',   'hsalazar@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Lead Engineer / DC')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'DC', 'dc_user',    'Karen Tan',        'dc_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Backup DC')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'DC', 'dc_alt',     'Raj Kumar',        'dc_alt@srxglobal.local',     TRUE, 'seed-dev-data.sql', 'Alternate DC')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── SE: Senior Engineer ────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'SE', 'eng_user',   'Nick Lim',         'eng_user@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Senior Engineer — SMT/PCB')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'SE', 'se_user2',   'Aisha Mohd',       'se_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Senior Engineer — Mechanical')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'SE', 'se_user3',   'Wei Lin',          'se_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Senior Engineer — Test')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── CE: Chief Engineer ─────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'CE', 'ce_user',    'Branko Petrovic',  'ce_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Chief Engineer')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'CE', 'ce_user2',   'Sandra Wong',      'ce_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Chief Engineer — Alternate')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'CE', 'ce_user3',   'Dinesh Nair',      'ce_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Chief Engineer — Deputy')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── EM: Engineering Manager ────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'EM', 'em_user',    'Karen Chen',       'em_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Engineering Manager')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'EM', 'em_user2',   'Thomas Ng',        'em_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Engineering Manager — Alternate')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'EM', 'em_user3',   'Priya Rajan',      'em_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Engineering Manager — Deputy')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── QM: Quality Manager ────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'QM', 'qm_user',    'Divya Sharma',     'qm_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Quality Manager')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'QM', 'qm_user2',   'Lee Mei Ling',     'qm_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Quality Manager — Alternate')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'QM', 'qm_user3',   'Ahmad Fadzil',     'qm_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Quality Engineer')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── PM: Production Manager ─────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'PM', 'pm_user',    'Jason Teo',        'pm_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Production Manager')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'PM', 'pm_user2',   'Siti Rahimah',     'pm_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Production Manager — Alternate')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'PM', 'pm_user3',   'Lim Boon Keat',    'pm_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Production Supervisor')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── SC: Supply Chain / Purchasing ──────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'SC', 'sc_user',    'Michelle Tan',     'sc_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Supply Chain Manager')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'SC', 'sc_user2',   'Farid Hassan',     'sc_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Purchasing Manager')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'SC', 'sc_user3',   'Chloe Yap',        'sc_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Buyer')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── FN: Finance ────────────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'FN', 'fn_user',    'Grace Lau',        'fn_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Finance Manager')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'FN', 'fn_user2',   'Azlan Ibrahim',    'fn_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Finance Controller')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'FN', 'fn_user3',   'Cindy Ho',         'fn_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Cost Analyst')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── CA: Cost Accountant ────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'CA', 'ca_user',    'Bernard Ong',      'ca_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Cost Accountant')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'CA', 'ca_user2',   'Nurul Ain',        'ca_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Cost Accountant — Alternate')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'CA', 'ca_user3',   'Steven Koh',       'ca_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Senior Cost Accountant')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── RD: R&D / Product Engineering (observer) ───────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'RD', 'rd_user',    'Victor Tan',       'rd_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'R&D Engineer')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'RD', 'rd_user2',   'Alicia Foo',       'rd_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Product Engineer')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'RD', 'rd_user3',   'Hafiz Zulkifli',   'rd_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Design Engineer')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── TE: Test Engineering (observer) ───────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'TE', 'te_user',    'Marcus Yee',       'te_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Test Engineer')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'TE', 'te_user2',   'Jasmine Loh',      'te_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Test Engineer — ICT')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'TE', 'te_user3',   'Ravi Subramaniam', 'te_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Test Engineer — Functional')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── MQ: Manufacturing Quality (observer) ──────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'MQ', 'mq_user',    'Jenny Chai',       'mq_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Manufacturing Quality Engineer')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'MQ', 'mq_user2',   'Zulhilmi Aris',    'mq_user2@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Process Quality Engineer')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'MQ', 'mq_user3',   'Patricia Yong',    'mq_user3@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'Quality Inspector')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- ── AD: Admin ─────────────────────────────────────────────────────────────
INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'AD', 'hsalazar',   'Hector Salazar',   'hsalazar@srxglobal.local',   TRUE, 'seed-dev-data.sql', 'System Administrator')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'AD', 'dc_user',    'Karen Tan',        'dc_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'Admin — DC backup')
ON CONFLICT (facility, role_id, username) DO NOTHING;

INSERT INTO system_role_users (facility, role_id, username, display_name, email, is_active, added_by, notes)
VALUES ('D', 'AD', 'ad_user',    'Manal Al-Rashid',  'ad_user@srxglobal.local',    TRUE, 'seed-dev-data.sql', 'IT Admin')
ON CONFLICT (facility, role_id, username) DO NOTHING;

-- Verify
SELECT facility, role_id, count(*) AS user_count,
       string_agg(username, ', ' ORDER BY username) AS usernames
FROM system_role_users
WHERE facility = 'D'
GROUP BY facility, role_id
ORDER BY role_id;
