/**
 * Oskar E2E — ECN BOM changes end-to-end (Slice E, I2-6, ADR-012)
 *
 * Covers:
 *  - Author a BOM change (CHANGE type) on a DRAFT ECN item via BOMChangesPanel
 *  - Submit -> the snapshot is captured (asserted indirectly: dc_approve
 *    later succeeds/fails based on whether the live BOM still matches it)
 *  - Drive the ECN to DC_APPROVED via the standard approval chain
 *  - movex_stub's live BOM is mutated on a CONFLICTING key (same component_
 *    number/operation_number this ECN's BOM change touches) between submit
 *    and dc_approve, via the stub's e2e-only _test-mutate endpoint
 *  - DC Approve is attempted -> blocked (409), diff banner shown in
 *    BOMChangesPanel's "bom" tab
 *  - The stub's BOM state is restored (_test-mutate/.../reset) -> DC
 *    Approve retried -> succeeds
 *
 * Requires the backend running with MOVEX_API_URL pointed at
 * scripts/movex_stub.py (per D7, ADR-012):
 *   uvicorn scripts.movex_stub:app --port 8100
 *   MOVEX_API_URL=http://localhost:8100 <start backend>
 *
 * Uses LFCONC0001-style parent item + LF200010 (the single_level.json
 * fixture's first component, OPNO 10) as the conflicting key, matching
 * tests/integration/test_concurrency_gate.py's backend-side coverage of the
 * identical scenario — this spec is the UI-level counterpart of that test.
 *
 * NOTE: matching the established precedent for this repo's BOM e2e specs
 * (see bom-compare.spec.ts's own disclosure, and bom-browser.spec.ts before
 * it) — this spec was authored to the existing e2e conventions
 * (helpers/api.ts + helpers/pages.ts) but could not be executed in the
 * sandboxed environment this slice was built in: no live frontend dev
 * server + backend + movex_stub trio was running simultaneously (the only
 * running backend container in this environment serves the dev database on
 * a different, non-worktree codebase snapshot, and no frontend dev server
 * or movex_stub instance was running at all). It has not been visually or
 * functionally verified; treat it as written-to-spec, not confirmed-green.
 * The backend-side behaviour it exercises (the concurrency gate itself,
 * 409 + diff payload, outbox queuing) IS fully verified — see
 * tests/integration/test_concurrency_gate.py (5/5 passing) and
 * tests/integration/test_queue_bom_changes_outbox.py (4/4 passing).
 */

import { test, expect } from "@playwright/test"
import {
  getToken, clearTokenCache, createECN, addItem, findItemId, addBomChange,
  fireTransition, approveRole, API_BASE,
} from "./helpers/api"
import { LoginPage, ECNDetailPage } from "./helpers/pages"

const PARENT_ITEM = "LF100001" // single_level.json fixture item (movex_stub)
const CONFLICTING_COMPONENT = "LF200010"
const CONFLICTING_OPNO = 10

test.beforeAll(async ({ request }) => {
  clearTokenCache()
  await getToken(request, "eng_user")
  await getToken(request, "dc_user")
  await getToken(request, "qm_user")
})

async function resetStubBom(request: import("@playwright/test").APIRequestContext) {
  // Best-effort cleanup — the stub may not be reachable in every environment
  // this spec runs in (e.g. no movex_stub configured); never fail the test
  // teardown on this.
  await request.post(`${process.env.MOVEX_STUB_URL ?? "http://localhost:8100"}/_test-mutate/bom/${PARENT_ITEM}/reset`).catch(() => {})
}

test.describe("ECN BOM changes — concurrency gate blocks then allows approval", () => {
  test.afterEach(async ({ request }) => {
    await resetStubBom(request)
  })

  test("live BOM mutated between submit and dc_approve blocks approval with a diff banner, then approving after restore succeeds", async ({ page, request }) => {
    const orToken = await getToken(request, "eng_user")
    const seToken = orToken // eng_user also holds SE in the seed config, matching workflow-full.spec.ts's convention
    const dcToken = await getToken(request, "dc_user")
    const qmToken = await getToken(request, "qm_user")

    // ── Build: DRAFT ECN with a BOM change against the parent item ─────────
    const ecn = await createECN(request, orToken, { title: "E2E BOM concurrency test" })
    await addItem(request, orToken, ecn.id, 10, PARENT_ITEM)
    const itemId = await findItemId(request, orToken, ecn.id, PARENT_ITEM)
    await addBomChange(request, orToken, ecn.id, itemId, {
      change_type: "CHANGE",
      component_number: CONFLICTING_COMPONENT,
      operation_number: CONFLICTING_OPNO,
      quantity: 6.0,
      from_date: 20260901,
      old_from_date: 20240101,
      old_quantity: 4.0,
    })

    // ── Submit (captures the snapshot) -> Engineering -> Management -> DC_APPROVED gate ──
    await fireTransition(request, orToken, ecn.id, "submit", "OR")
    await fireTransition(request, seToken, ecn.id, "approve_engineering", "SE")
    await approveRole(request, qmToken, ecn.id, "QM")

    // ── Mutate the live BOM on the SAME key this ECN's change touches ──────
    const mutateBase = process.env.MOVEX_STUB_URL ?? "http://localhost:8100"
    const currentBom = await (await request.get(`${mutateBase}/api/bom/${PARENT_ITEM}`)).json()
    const mutatedBom = {
      data: {
        head: currentBom.data.head,
        records: currentBom.data.records.map((r: any) =>
          r.MTNO === CONFLICTING_COMPONENT && r.OPNO === CONFLICTING_OPNO
            ? { ...r, CNQT: 999.0 }
            : r,
        ),
      },
    }
    await request.post(`${mutateBase}/_test-mutate/bom/${PARENT_ITEM}`, { data: mutatedBom })

    // ── Attempt DC Approve via the UI -> expect a block + diff banner ──────
    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("dc_user")

    const detail = new ECNDetailPage(page)
    await detail.goto(ecn.id)
    await detail.clickHeaderButton(/dc approve/i)

    await detail.waitForError()
    const errorText = await detail.errorBannerText()
    expect(errorText).toMatch(/changed|conflict/i)

    // Status must NOT have advanced past DC_APPROVED (the gate blocks
    // before persisting — see test_concurrency_gate.py's backend coverage
    // of the identical assertion).
    await expect(page.locator("header")).toContainText(/dc.?approved/i)

    // Open the item panel's BOM tab and confirm the conflict banner (diff
    // table) rendered — see BOMChangesPanel.tsx's conflictDiff prop, fed
    // from ECNDetailPage's transition.error via transitionBomConflict().
    await page.getByText(PARENT_ITEM).first().click()
    await page.getByRole("button", { name: /bom changes/i }).click()
    await expect(page.getByText(/bom changed since submission/i)).toBeVisible()

    // ── Restore the live BOM and retry -> approval succeeds ────────────────
    await request.post(`${mutateBase}/_test-mutate/bom/${PARENT_ITEM}/reset`)

    await page.getByRole("button", { name: /close/i }).first().click().catch(() => {})
    await detail.clickHeaderButton(/dc approve/i)

    await expect(page.locator("header")).not.toContainText(/dc.?approved/i, { timeout: 12_000 })
  })
})
