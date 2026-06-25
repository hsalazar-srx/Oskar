/**
 * Oskar E2E — Full happy-path workflow
 *
 * Covers: DRAFT → ENGINEERING_REVIEW → MANAGEMENT_REVIEW → DC_APPROVED → APPROVED
 *
 * Users:
 *   eng_user  — Originator (OR) + Systems Engineer (SE)
 *   qm_user   — Quality Manager (QM)
 *   dc_user   — Document Controller (DC)
 *
 * Each test builds on API pre-conditions so only the stage under test goes
 * through the UI. The "end-to-end sequence" test drives every step via UI.
 */

import { test, expect } from "@playwright/test"
import {
  API_BASE,
  getToken,
  clearTokenCache,
  ecnAtDraft,
  ecnAtEngReview,
  ecnAtMgmtReview,
  ecnAtDCApproved,
  fireTransition,
  approveRole,
} from "./helpers/api"
import { LoginPage, ECNListPage, ECNDetailPage, ECNCreatePage } from "./helpers/pages"

// ── shared tokens (lazy-loaded once per file) ──────────────────────────────────
let engToken: string
let qmToken: string
let dcToken: string

test.beforeAll(async ({ request }) => {
  clearTokenCache()
  engToken = await getToken(request, "eng_user")
  qmToken  = await getToken(request, "qm_user")
  dcToken  = await getToken(request, "dc_user")
})

// ── Helper: log in as a user and go to an ECN detail page ─────────────────────
async function loginAndOpenECN(page: any, username: string, ecnId: string) {
  const login = new LoginPage(page)
  await login.goto()
  await login.loginAndExpectList(username)
  const detail = new ECNDetailPage(page)
  await detail.goto(ecnId)
  return detail
}

// ─────────────────────────────────────────────────────────────────────────────
// Stage 1 — Create ECN and submit for engineering review
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Stage 1 — DRAFT → ENGINEERING_REVIEW", () => {
  test("eng_user creates ECN via UI and submits for review", async ({ page }) => {
    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("eng_user")

    const list = new ECNListPage(page)
    await list.navigateToNewECN()

    const createPage = new ECNCreatePage(page)
    await createPage.fill({ title: "E2E Full Workflow — UI Create" })

    const ecnId = await createPage.submit()
    expect(ecnId).toMatch(/^[0-9a-f-]{36}$/)

    const detail = new ECNDetailPage(page)
    await detail.waitForLoaded()

    // Status should be DRAFT (0) initially
    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("draft")

    // Add an item before submitting
    await detail.addItemViaPanel("E2E-001")

    // Submit for review via header button
    await detail.clickHeaderButton(/submit for review/i)
    await detail.waitForToast()

    const newBadge = await detail.statusBadgeText()
    expect(newBadge.toLowerCase()).toContain("engineering")
  })

  test("DRAFT ECN shows Submit for Review button only for originator", async ({ page, request }) => {
    const { ecnId } = await ecnAtDraft(request, engToken)

    // eng_user (originator) sees Submit button
    const detail = await loginAndOpenECN(page, "eng_user", ecnId)
    const submitBtn = page.locator("header").getByRole("button", { name: /submit for review/i })
    await expect(submitBtn).toBeVisible()
  })

  test("DRAFT ECN has no action buttons for qm_user", async ({ page, request }) => {
    const { ecnId } = await ecnAtDraft(request, engToken)

    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("qm_user")

    const detail = new ECNDetailPage(page)
    await detail.goto(ecnId)

    // No header action buttons should be visible for QM on a DRAFT ECN
    const headerBtns = page.locator("header").getByRole("button").filter({ hasText: /submit|approve|reject/i })
    await expect(headerBtns).toHaveCount(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Stage 2 — ENGINEERING_REVIEW → MANAGEMENT_REVIEW
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Stage 2 — ENGINEERING_REVIEW → MANAGEMENT_REVIEW", () => {
  test("eng_user (as SE) approves engineering review via UI", async ({ page, request }) => {
    const { ecnId } = await ecnAtEngReview(request, engToken)

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    // Header should show Approve Engineering Review
    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("engineering")

    await detail.clickHeaderButton(/approve engineering/i)
    await detail.waitForToast()

    const newBadge = await detail.statusBadgeText()
    expect(newBadge.toLowerCase()).toContain("management")
  })

  test("eng_user can reject at engineering review — modal required", async ({ page, request }) => {
    const { ecnId } = await ecnAtEngReview(request, engToken)

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    // Reject is in the panel footer, not the header
    await detail.clickPanelAction(/reject/i)

    // Reject modal should appear
    await page.waitForSelector("[role='dialog']", { timeout: 5_000 })
    await detail.fillModalField(/rejection reason/i, "E2E test — rejecting at engineering stage")
    await detail.confirmModal(/reject/i)
    await detail.waitForToast()

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("reject")
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Stage 3 — MANAGEMENT_REVIEW parallel approvals
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Stage 3 — MANAGEMENT_REVIEW parallel approvals", () => {
  test("qm_user sees Approve as QM button in workflow panel", async ({ page, request }) => {
    const { ecnId } = await ecnAtMgmtReview(request, engToken, engToken)

    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("qm_user")

    const detail = new ECNDetailPage(page)
    await detail.goto(ecnId)

    // The Approve as QM button should appear in the WorkflowPanel
    const approveBtn = page.locator(".rounded-lg.border")
      .filter({ hasText: /ecn workflow/i })
      .getByRole("button", { name: /approve as/i })
    await expect(approveBtn).toBeVisible()
  })

  test("qm_user approves their step → ECN moves to DC_APPROVED", async ({ page, request }) => {
    const { ecnId } = await ecnAtMgmtReview(request, engToken, engToken)

    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("qm_user")

    const detail = new ECNDetailPage(page)
    await detail.goto(ecnId)

    await detail.clickApproveRoleButton()
    await detail.waitForToast()

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toMatch(/dc.?approved|dc approved/i)
  })

  test("qm_user does NOT see Approve as QM if already approved", async ({ page, request }) => {
    const { ecnId } = await ecnAtMgmtReview(request, engToken, engToken)
    // Pre-approve as QM via API
    await approveRole({ post: async (url: string, opts: any) => {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Authorization": `Bearer ${qmToken}`, "Content-Type": "application/json" },
        body: JSON.stringify(opts.data ?? {}),
      })
      return { ok: () => res.ok, status: () => res.status, text: async () => res.text(), json: async () => res.json() }
    } } as any, qmToken, ecnId, "QM")

    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("qm_user")

    const detail = new ECNDetailPage(page)
    await detail.goto(ecnId)

    // No "Approve as" button since QM step is done
    const approveBtn = page.locator(".rounded-lg.border")
      .filter({ hasText: /ecn workflow/i })
      .getByRole("button", { name: /approve as/i })
    await expect(approveBtn).toHaveCount(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Stage 4 — DC_APPROVED → APPROVED
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Stage 4 — DC_APPROVED → APPROVED", () => {
  test("dc_user sees DC Approve button and approves", async ({ page, request }) => {
    const { ecnId } = await ecnAtDCApproved(request, engToken, engToken, qmToken)

    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("dc_user")

    const detail = new ECNDetailPage(page)
    await detail.goto(ecnId)

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toMatch(/dc.?approved|dc approved/i)

    // DC Approve header button
    await detail.clickHeaderButton(/dc approve/i)
    await detail.waitForToast()

    const newBadge = await detail.statusBadgeText()
    expect(newBadge.toLowerCase()).toContain("approved")
  })

  test("non-dc user does NOT see DC Approve button", async ({ page, request }) => {
    const { ecnId } = await ecnAtDCApproved(request, engToken, engToken, qmToken)

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    const dcApproveBtn = page.locator("header").getByRole("button", { name: /dc approve/i })
    await expect(dcApproveBtn).toHaveCount(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Stage 5 — APPROVED → IMPLEMENTED → CLOSED
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Stage 5 — APPROVED → IMPLEMENTED → CLOSED", () => {
  test("eng_user marks approved ECN as implemented", async ({ page, request }) => {
    // Build to DC_APPROVED via API, then dc_approve via API, then test Implement via UI
    const { ecnId } = await ecnAtDCApproved(request, engToken, engToken, qmToken)
    await fireTransition(request, dcToken, ecnId, "dc_approve", "DC")

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("approved")

    await detail.clickHeaderButton(/mark as implemented|implement/i)
    await detail.waitForToast()

    const newBadge = await detail.statusBadgeText()
    expect(newBadge.toLowerCase()).toContain("implement")
  })

  test("eng_user closes an implemented ECN", async ({ page, request }) => {
    const { ecnId } = await ecnAtDCApproved(request, engToken, engToken, qmToken)
    await fireTransition(request, dcToken, ecnId, "dc_approve", "DC")
    await fireTransition(request, engToken, ecnId, "implement", "OR")

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("implement")

    await detail.clickHeaderButton(/close/i)
    await detail.waitForToast()

    const newBadge = await detail.statusBadgeText()
    expect(newBadge.toLowerCase()).toContain("closed")
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// End-to-end: full UI sequence (no API shortcuts)
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Full UI sequence — DRAFT to APPROVED", () => {
  test("completes entire workflow through UI only", async ({ browser }) => {
    // We need three separate browser contexts (three different logged-in users)
    const engCtx = await browser.newContext()
    const qmCtx  = await browser.newContext()
    const dcCtx  = await browser.newContext()

    const engPage = await engCtx.newPage()
    const qmPage  = await qmCtx.newPage()
    const dcPage  = await dcCtx.newPage()

    try {
      // --- eng_user: create ECN ---
      const loginEng = new LoginPage(engPage)
      await loginEng.goto()
      await loginEng.loginAndExpectList("eng_user")

      const list = new ECNListPage(engPage)
      await list.navigateToNewECN()

      const createPg = new ECNCreatePage(engPage)
      await createPg.fill({ title: "E2E Full Sequence — no API shortcuts" })
      const ecnId = await createPg.submit()

      const engDetail = new ECNDetailPage(engPage)
      await engDetail.waitForLoaded()

      // Add item
      await engDetail.addItemViaPanel("E2E-SEQ-001")

      // Submit for review
      await engDetail.clickHeaderButton(/submit for review/i)
      await engDetail.waitForToast()
      expect((await engDetail.statusBadgeText()).toLowerCase()).toContain("engineering")

      // --- eng_user (as SE): approve engineering review ---
      await engDetail.clickHeaderButton(/approve engineering/i)
      await engDetail.waitForToast()
      expect((await engDetail.statusBadgeText()).toLowerCase()).toContain("management")

      // --- qm_user: approve QM step ---
      const loginQM = new LoginPage(qmPage)
      await loginQM.goto()
      await loginQM.loginAndExpectList("qm_user")

      const qmDetail = new ECNDetailPage(qmPage)
      await qmDetail.goto(ecnId)
      expect((await qmDetail.statusBadgeText()).toLowerCase()).toContain("management")

      await qmDetail.clickApproveRoleButton()
      await qmDetail.waitForToast()
      expect((await qmDetail.statusBadgeText()).toLowerCase()).toMatch(/dc.?approved|dc approved/i)

      // --- dc_user: final DC approval ---
      const loginDC = new LoginPage(dcPage)
      await loginDC.goto()
      await loginDC.loginAndExpectList("dc_user")

      const dcDetail = new ECNDetailPage(dcPage)
      await dcDetail.goto(ecnId)
      expect((await dcDetail.statusBadgeText()).toLowerCase()).toMatch(/dc.?approved|dc approved/i)

      await dcDetail.clickHeaderButton(/dc approve/i)
      await dcDetail.waitForToast()
      expect((await dcDetail.statusBadgeText()).toLowerCase()).toContain("approved")
    } finally {
      await engCtx.close()
      await qmCtx.close()
      await dcCtx.close()
    }
  })
})
