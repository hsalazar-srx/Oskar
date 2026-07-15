#!/usr/bin/env bash
# OSKAR — Fire a workflow trigger on an ECN via the real API (dev/local testing)
#
# Handles login + If-Unmodified-Since header automatically so you can drive an
# ECN through DRAFT -> ... -> IMPLEMENTED one trigger at a time from the shell,
# without hand-building curl calls each time. Built while live-testing the
# dc_approve -> Movex write flow (S9-7).
#
# Usage:
#   ./scripts/ecn-transition.sh <ecn_id> <username> <trigger> <actor_role> [extra_json_fields]
#
# Examples:
#   ./scripts/ecn-transition.sh 4d900b7f-... hsalazar submit OR
#   ./scripts/ecn-transition.sh 4d900b7f-... eng_user approve_engineering SE
#   ./scripts/ecn-transition.sh 4d900b7f-... eng_user approve_role EM '"role_id": "EM"'
#   ./scripts/ecn-transition.sh 4d900b7f-... dc_user dc_approve DC
#
# extra_json_fields is inserted verbatim as additional top-level JSON fields
# in the request body (e.g. role_id for approve_role, rejection_reason for
# reject) — pass it WITHOUT surrounding braces, as shown above.
#
# Environment variables:
#   OSKAR_API_URL  — default http://localhost:8000
#   OSKAR_PASSWORD — default "password" (dev auth bypass — AUTH_PROVIDER=dev)
#
# Full happy-path sequence (plain ECN, no routing/MPN changes):
#   submit (OR) -> approve_engineering (SE) -> approve_role EM -> approve_role QM
#   -> complete_management_review (QM) -> dc_approve (DC)
# Facilities with routing_changes=true also require approve_role PM.
# Trigger/role requirements are data-driven per facility — see
# ecn_step_conditions in the DB, or ai/tasks/sprint-backlog.md S9-7 for context.

set -euo pipefail

if [ "$#" -lt 4 ]; then
    echo "Usage: $0 <ecn_id> <username> <trigger> <actor_role> [extra_json_fields]" >&2
    exit 1
fi

ECN_ID="$1"
USER="$2"
TRIGGER="$3"
ACTOR_ROLE="$4"
EXTRA_JSON="${5:-}"

BASE_URL="${OSKAR_API_URL:-http://localhost:8000}"
PASSWORD="${OSKAR_PASSWORD:-password}"

TOKEN=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

UPDATED_AT=$(curl -s "$BASE_URL/api/v1/ecn/$ECN_ID" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['updated_at'])")

IF_UNMODIFIED_SINCE=$(python3 -c "
from datetime import datetime
dt = datetime.fromisoformat('$UPDATED_AT'.replace('Z', '+00:00'))
print(dt.strftime('%a, %d %b %Y %H:%M:%S GMT'))
")

BODY="{\"trigger\": \"$TRIGGER\", \"actor_role\": \"$ACTOR_ROLE\""
if [ -n "$EXTRA_JSON" ]; then
    BODY="$BODY, $EXTRA_JSON"
fi
BODY="$BODY}"

echo ">>> As $USER: trigger=$TRIGGER actor_role=$ACTOR_ROLE ecn_id=$ECN_ID"

curl -s -X PATCH "$BASE_URL/api/v1/ecn/$ECN_ID/status" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "If-Unmodified-Since: $IF_UNMODIFIED_SINCE" \
  -d "$BODY" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'detail' in d and 'status_name' not in d:
    print('ERROR:', d['detail'])
    sys.exit(1)
else:
    print('status:', d.get('status'), d.get('status_name'))
"
