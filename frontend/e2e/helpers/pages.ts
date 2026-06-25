/**
 * Oskar E2E — Page Object Models
 *
 * LoginPage      — /login
 * ECNListPage    — /ecn
 * ECNDetailPage  — /ecn/:id
 *
 * Each POM exposes high-level actions (fill, click, wait) so spec files
 * read as plain English rather than locator chains.
 */

import { Page, expect } from "@playwright/test"

// ── LoginPage ─────────────────────────────────────────────────────────────────

export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/login")
    await this.page.waitForURL("**/login")
  }

  async login(username: string, password = "dev-password") {
    await this.page.getByLabel(/username/i).fill(username)
    await this.page.getByLabel(/password/i).fill(password)
    await this.page.getByRole("button", { name: /sign in|login/i }).click()
    // Wait for redirect away from /login
    await this.page.waitForURL((url) => !url.pathname.includes("login"), { timeout: 10_000 })
  }

  async loginAndExpectList(username: string, password = "dev-password") {
    await this.login(username, password)
    await expect(this.page).toHaveURL(/\/ecn/)
  }
}

// ── ECNListPage ───────────────────────────────────────────────────────────────

export class ECNListPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/ecn")
    await this.page.waitForURL("**/ecn")
  }

  async waitForLoaded() {
    // Table renders once data arrives; wait for at least the header row
    await this.page.waitForSelector("table", { timeout: 10_000 })
  }

  async clickECN(ecnNumber: string) {
    await this.page.getByRole("link", { name: ecnNumber }).click()
    await this.page.waitForURL(`**/ecn/**`)
  }

  async navigateToNewECN() {
    await this.page.getByRole("button", { name: /new ecn/i }).click()
    await this.page.waitForURL("**/ecn/new")
  }

  async signOut() {
    await this.page.getByRole("button", { name: /sign out/i }).click()
    await this.page.waitForURL("**/login")
  }

  /** Returns the current stat strip counts */
  async statCounts(): Promise<{ active: number; myAction: number; overdue: number }> {
    const cards = this.page.locator(".rounded-lg.border")
    const active   = Number(await cards.nth(0).locator(".text-2xl").textContent())
    const myAction = Number(await cards.nth(1).locator(".text-2xl").textContent())
    const overdue  = Number(await cards.nth(2).locator(".text-2xl").textContent())
    return { active, myAction, overdue }
  }
}

// ── ECNDetailPage ─────────────────────────────────────────────────────────────

export class ECNDetailPage {
  constructor(private page: Page) {}

  async goto(ecnId: string) {
    await this.page.goto(`/ecn/${ecnId}`)
    await this.page.waitForURL(`**/ecn/${ecnId}`)
    await this.waitForLoaded()
  }

  async waitForLoaded() {
    // ECN number appears in the sticky header once data loads
    await this.page.waitForSelector("header .font-mono", { timeout: 10_000 })
  }

  // ── Header reads ────────────────────────────────────────────────────────────

  async ecnNumber(): Promise<string> {
    return (await this.page.locator("header .font-mono").first().textContent()) ?? ""
  }

  async statusBadgeText(): Promise<string> {
    return (await this.page.locator("header .badge, header [class*='badge']").first().textContent()) ?? ""
  }

  // ── Header actions ──────────────────────────────────────────────────────────

  /** Click the primary header action button (Submit, Resubmit, DC Approve, Resume) */
  async clickHeaderButton(label: string | RegExp) {
    await this.page.locator("header").getByRole("button", { name: label }).click()
    await this.waitForTransition()
  }

  /** Click a confirm dialog that appears (window.confirm override) */
  async acceptConfirmDialog() {
    this.page.once("dialog", (d) => d.accept())
  }

  // ── Panel actions ───────────────────────────────────────────────────────────

  /** Click the Approve as <role> button in the workflow panel header */
  async clickApproveRoleButton() {
    await this.page
      .locator(".rounded-lg.border")
      .filter({ hasText: /ecn workflow/i })
      .getByRole("button", { name: /approve as/i })
      .click()
    await this.waitForTransition()
  }

  /** Click a panel footer action (Reject, Place on Hold) */
  async clickPanelAction(label: string | RegExp) {
    const panel = this.page.locator(".rounded-lg.border").filter({ hasText: /ecn workflow/i })
    await panel.locator(".border-t").getByRole("button", { name: label }).click()
  }

  // ── Modal interactions ──────────────────────────────────────────────────────

  async fillModalField(placeholder: string | RegExp, value: string) {
    await this.page.getByPlaceholder(placeholder).fill(value)
  }

  async fillModalDate(name: string, value: string) {
    await this.page.locator(`input[name="${name}"]`).fill(value)
  }

  async confirmModal(confirmLabel: string | RegExp = /confirm|submit|reject|place on hold/i) {
    await this.page.getByRole("button", { name: confirmLabel }).click()
    await this.waitForTransition()
  }

  async cancelModal() {
    await this.page.getByRole("button", { name: /cancel/i }).click()
  }

  // ── Error banner ────────────────────────────────────────────────────────────

  async errorBannerText(): Promise<string | null> {
    const banner = this.page.locator(".border-red-200").first()
    if (await banner.count() === 0) return null
    return banner.textContent()
  }

  async waitForError() {
    await this.page.locator(".border-red-200").waitFor({ state: "visible", timeout: 8_000 })
  }

  // ── Toast ───────────────────────────────────────────────────────────────────

  async waitForToast() {
    await this.page.locator(".border-green-200").waitFor({ state: "visible", timeout: 10_000 })
  }

  async toastText(): Promise<string> {
    return (await this.page.locator(".border-green-200").textContent()) ?? ""
  }

  // ── Items ───────────────────────────────────────────────────────────────────

  async addItemViaPanel(itemNumber: string, itemName = "E2E Part") {
    await this.page.getByRole("button", { name: /add item/i }).click()
    await this.page.waitForSelector("[data-state='open']", { timeout: 5_000 })
    await this.page.getByLabel(/item number/i).fill(itemNumber)
    await this.page.getByLabel(/item name/i).fill(itemName)
    await this.page.getByRole("button", { name: /save/i }).click()
    await this.page.waitForSelector("[data-state='open']", { state: "hidden", timeout: 8_000 })
  }

  // ── Approval steps (Management Review panel) ────────────────────────────────

  async approvalStepStatuses(): Promise<Record<string, string>> {
    const steps: Record<string, string> = {}
    const rows = this.page.locator(".rounded-md.border").filter({ hasText: /QM|SE|EM|PM|SC|FN|CE/ })
    for (const row of await rows.all()) {
      const roleId = (await row.locator(".font-mono").first().textContent())?.trim() ?? ""
      const status = (await row.locator(".badge, [class*='badge']").first().textContent())?.trim() ?? ""
      steps[roleId] = status
    }
    return steps
  }

  // ── Internal ────────────────────────────────────────────────────────────────

  /** Wait for a network request to /status to complete (transition round-trip) */
  async waitForTransition() {
    await Promise.race([
      this.page.waitForResponse((r) => r.url().includes("/status") && r.status() < 500, { timeout: 12_000 }),
      this.page.waitForResponse((r) => r.url().includes("/approve") && r.status() < 500, { timeout: 12_000 }),
    ]).catch(() => {
      // No /status or /approve call — transition may have been handled differently
    })
    // Let React re-render settle
    await this.page.waitForTimeout(400)
  }
}

// ── ECNCreatePage ─────────────────────────────────────────────────────────────

export class ECNCreatePage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/ecn/new")
    await this.page.waitForURL("**/ecn/new")
  }

  async fill(fields: {
    title: string
    customer?: string
    facility?: string
    isNewItem?: boolean
  }) {
    await this.page.getByLabel(/title/i).fill(fields.title)
    if (fields.customer) {
      const sel = this.page.getByLabel(/customer/i)
      if (await sel.count() > 0) await sel.fill(fields.customer)
    }
    if (fields.isNewItem) {
      await this.page.getByLabel(/new item/i).check()
    }
  }

  async submit(): Promise<string> {
    await this.page.getByRole("button", { name: /create|save|submit/i }).click()
    await this.page.waitForURL(/\/ecn\/[0-9a-f-]{36}$/, { timeout: 10_000 })
    // Return the ECN ID from the URL
    return this.page.url().split("/ecn/")[1]
  }
}
