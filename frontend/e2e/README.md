# Oskar E2E Tests

Playwright tests covering the full ECN workflow from DRAFT to CLOSED.

## Prerequisites

Both services must be running before you start tests:

```bash
# Terminal 1 — backend (with dev auth provider)
cd c:\Projects\Oskar\backend
AUTH_PROVIDER=dev uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd c:\Projects\Oskar\frontend
npm run dev
```

Playwright must be installed (it is already in `devDependencies`):

```bash
npx playwright install chromium
```

## Dev users

The tests expect these users to exist in the `DEV_USERS` env var (or seeded in the database):

| Username   | Roles / Groups        | Used for                     |
|------------|-----------------------|------------------------------|
| `eng_user` | OR, SE, OSKAR-ENG     | Originator + Engineering SE  |
| `qm_user`  | QM, OSKAR-QM          | Quality Manager approvals    |
| `dc_user`  | DC, OSKAR-DC          | Document Controller sign-off |
| `hsalazar` | All groups (admin)    | Auth tests                   |

All dev users authenticate with password `dev-password`.

## Running tests

```bash
# Run all E2E tests
npm run e2e

# Run with browser visible
npm run e2e:headed

# Run only auth tests
npm run e2e:auth

# Run only workflow tests (full + rejection + guards)
npm run e2e:workflow

# Open Playwright UI (interactive, great for debugging)
npm run e2e:ui

# Open the HTML report from the last run
npm run e2e:report
```

## Environment overrides

| Variable   | Default                  | Purpose                    |
|------------|--------------------------|----------------------------|
| `BASE_URL` | `http://localhost:5173`  | Frontend URL               |
| `API_URL`  | `http://localhost:8000`  | Backend URL (API helpers)  |

Example:
```bash
BASE_URL=http://localhost:4173 API_URL=http://localhost:8000 npm run e2e
```

## Test files

| File                          | Coverage                                              |
|-------------------------------|-------------------------------------------------------|
| `auth.spec.ts`                | Login, logout, wrong password, session persistence    |
| `workflow-full.spec.ts`       | DRAFT → ENGINEERING → MANAGEMENT → DC_APPROVED → APPROVED → IMPLEMENTED → CLOSED |
| `workflow-rejection.spec.ts`  | Reject at ENG/MGMT, resubmit, cancel, on-hold/resume |
| `workflow-guards.spec.ts`     | 422 role guard (API + UI), 409 optimistic lock, button visibility |

## Architecture

### Helpers (`e2e/helpers/`)

- **`api.ts`** — Direct API calls: token acquisition, ECN creation, transitions, per-stage pre-condition builders (`ecnAtDraft`, `ecnAtEngReview`, `ecnAtMgmtReview`, `ecnAtDCApproved`, `ecnAtRejected`).
- **`pages.ts`** — Page Object Models: `LoginPage`, `ECNListPage`, `ECNDetailPage`, `ECNCreatePage`.

### Design principles

- **Serial execution** (`workers: 1`) — workflow tests share database state; parallel workers would produce flaky results.
- **API pre-conditions** — Tests for stage N use API helpers to reach stage N−1 rather than driving the UI from scratch. This keeps each test focused on one transition.
- **Token cache** — JWT tokens are acquired once per test file (`test.beforeAll`) and reused to avoid repeated login round-trips.
- **Retry-once on 409** — `fireTransition` in both the UI layer (`src/api/ecn.ts`) and the API helper (`e2e/helpers/api.ts`) automatically retries with the `current_updated_at` from the 409 response body.

## Debugging failures

1. **Run with `--headed`** to see the browser: `npm run e2e:headed`
2. **Playwright UI** (`npm run e2e:ui`) lets you step through each action and inspect snapshots.
3. **Traces and screenshots** are saved on failure to `test-results/`. Open with `npx playwright show-trace`.
4. **Check backend logs** — 422 and 409 errors from the API include detail messages that the UI surface may not fully show.
