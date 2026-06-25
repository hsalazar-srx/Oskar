/**
 * Oskar E2E — Rejection and resubmit flows
 *
 * Covers:
 *  - Reject at ENGINEERING_REVIEW → status REJECTED
 *  - Reject at MANAGEMENT_REVIEW (QM) → status REJECTED
 *  - Originator resubmits rejected ECN with `restart` trigger
 *  - Originator uses `proceed` after rejection (if available)
 *  - CANCELLED flow (originator cancels from DRAFT)
 *  - ON_HOLD → RESUME flow
 */

import { test, expect } from "@playwright/test"
import {
  getToken,
  clearTokenCache,
  ecnAtDraft,
  ecnAtEngReview,
  ecnAtMgmtReview,
  ecnAtRejected,
  fireTransition,
  approveRole,
} from "./helpers/api"
import { LoginPage, ECNDetailPage } from "./helpers/pages"

let engToken: string
let qmToken:  string

test.beforeAll(async ({ request }) => {
  clearTokenCache()
  engToken = await getToken(request, "eng_user")
  qmToken  = await getToken(request, "qm_user")
})

async function loginAndOpenECN(page: any, username: string, ecnId: string): Promise<ECNDetailPage> {
  const login = new LoginPage(page)
  await login.goto()
  await login.loginAndExpectList(username)
  const detail = new ECNDetailPage(page)
  await detail.goto(ecnId)
  return detail
}

// ─────────────────────────────────────────────────────────────────────────────
// Reject at Engineering Review
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Reject at Engineering Review", () => {
  test("SE rejects → status becomes REJECTED", async ({ page, request }) => {
    const { ecnId } = await ecnAtEngReview(request, engToken)

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    // Reject is in the workflow panel footer
    await detail.clickPanelAction(/reject/i)

    // Wait for reject modal
    await page.waitForSelector("[role='dialog']", { timeout: 5_000 })
    await detail.fillModalField(/rejection reason/i, "Fails design spec — E2E test")
    await detail.confirmModal(/reject/i)
    await detail.waitForToast()

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("reject")
  })

  test("rejected ECN shows the rejection reason in the workflow panel", async ({ page, request }) => {
    const { ecnId } = await ecnAtRejected(request, engToken, engToken)

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    const panel = page.locator(".rounded-lg.border").filter({ hasText: /ecn workflow/i })
    await expect(panel.getByText(/rejection reason/i)).toBeVisible()
    await expect(panel.getByText(/E2E test rejection/i)).toBeVisible()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Reject at Management Review
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Reject at Management Review", () => {
  test("QM rejects from MANAGEMENT_REVIEW → REJECTED", async ({ page, request }) => {
    const { ecnId } = await ecnAtMgmtReview(request, engToken, engToken)

    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("qm_user")

    const detail = new ECNDetailPage(page)
    await detail.goto(ecnId)

    await detail.clickPanelAction(/reject/i)

    await page.waitForSelector("[role='dialog']", { timeout: 5_000 })
    await detail.fillModalField(/rejection reason/i, "QM rejects — quality concern — E2E")
    await detail.confirmModal(/reject/i)
    await detail.waitForToast()

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("reject")
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Resubmit after rejection
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Resubmit after rejection", () => {
  test("originator resubmits with restart → ENGINEERING_REVIEW", async ({ page, request }) => {
    const { ecnId } = await ecnAtRejected(request, engToken, engToken)

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("reject")

    // Resubmit header button
    await detail.clickHeaderButton(/resubmit/i)
    await detail.waitForToast()

    const newBadge = await detail.statusBadgeText()
    // Restart goes back to ENGINEERING_REVIEW
    expect(newBadge.toLowerCase()).toContain("engineering")
  })

  test("resubmit button is not visible to non-originator", async ({ page, request }) => {
    const { ecnId } = await ecnAtRejected(request, engToken, engToken)

    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("qm_user")

    const detail = new ECNDetailPage(page)
    await detail.goto(ecnId)

    const resubmitBtn = page.locator("header").getByRole("button", { name: /resubmit/i })
    await expect(resubmitBtn).toHaveCount(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Cancel flow
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Cancel flow", () => {
  test("originator can cancel a DRAFT ECN", async ({ page, request }) => {
    const { ecnId } = await ecnAtDraft(request, engToken)

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    // Cancel is in the workflow panel footer
    await detail.clickPanelAction(/cancel/i)

    // May require a confirm dialog or modal
    const dialogPromise = page.waitForEvent("dialog", { timeout: 2_000 }).catch(() => null)
    const dialog = await dialogPromise
    if (dialog) await dialog.accept()

    // If it's a modal (not browser dialog), confirm it
    const modalBtn = page.getByRole("button", { name: /confirm|cancel ecn/i })
    if (await modalBtn.count() > 0) {
      await modalBtn.click()
    }

    await detail.waitForToast()

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("cancel")
  })

  test("CANCELLED ECN has no workflow action buttons", async ({ page, request }) => {
    const { ecnId } = await ecnAtDraft(request, engToken)
    await fireTransition(request, engToken, ecnId, "cancel", "OR")

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    const actionBtns = page.locator("header").getByRole("button").filter({
      hasText: /submit|approve|reject|implement|close/i,
    })
    await expect(actionBtns).toHaveCount(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// On Hold / Resume flow
// ─────────────────────────────────────────────────────────────────────────────

test.describe("On Hold and Resume", () => {
  test("originator places ECN on hold — modal requires reason and date", async ({ page, request }) => {
    const { ecnId } = await ecnAtEngReview(request, engToken)

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    // Place on Hold is in the panel footer
    await detail.clickPanelAction(/hold/i)

    await page.waitForSelector("[role='dialog']", { timeout: 5_000 })

    // Fill hold reason and expected resume date
    await detail.fillModalField(/hold reason/i, "Waiting for supplier quote — E2E")
    await detail.fillModalDate("date", "2027-01-15")

    await detail.confirmModal(/place on hold/i)
    await detail.waitForToast()

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("hold")
  })

  test("originator resumes an on-hold ECN", async ({ page, request }) => {
    const { ecnId } = await ecnAtEngReview(request, engToken)
    await fireTransition(request, engToken, ecnId, "hold", "OR", {
      hold_reason: "E2E test hold",
      expected_resume_date: "2027-06-01",
    })

    const detail = await loginAndOpenECN(page, "eng_user", ecnId)

    const badge = await detail.statusBadgeText()
    expect(badge.toLowerCase()).toContain("hold")

    await detail.clickHeaderButton(/resume/i)
    await detail.waitForToast()

    const newBadge = await detail.statusBadgeText()
    expect(newBadge.toLowerCase()).toContain("engineering")
  })
})
