/**
 * Oskar E2E — Authentication flows
 *
 * Tests:
 *  - Valid login redirects to ECN list
 *  - Wrong password shows an error
 *  - Unknown user shows an error
 *  - Sign-out clears session and redirects to login
 *  - Unauthenticated navigation to /ecn redirects to /login
 */

import { test, expect } from "@playwright/test"
import { LoginPage, ECNListPage } from "./helpers/pages"

test.describe("Authentication", () => {
  test("valid login redirects to ECN list", async ({ page }) => {
    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("hsalazar")

    // Should see the ECN list header
    await expect(page.getByText(/engineering changes/i)).toBeVisible()
  })

  test("wrong password shows error", async ({ page }) => {
    const login = new LoginPage(page)
    await login.goto()

    await page.getByLabel(/username/i).fill("hsalazar")
    await page.getByLabel(/password/i).fill("wrong-password")
    await page.getByRole("button", { name: /sign in|login/i }).click()

    // Should stay on /login and show an error
    await expect(page).toHaveURL(/login/)
    await expect(page.locator(".text-red, .border-red, [class*='error'], [class*='alert']").first()).toBeVisible({ timeout: 5_000 })
  })

  test("empty password is rejected", async ({ page }) => {
    const login = new LoginPage(page)
    await login.goto()

    await page.getByLabel(/username/i).fill("hsalazar")
    // Leave password empty
    await page.getByRole("button", { name: /sign in|login/i }).click()

    // Either a client-side validation error or a 401 from the server
    await expect(page).toHaveURL(/login/)
  })

  test("sign out clears session and redirects to login", async ({ page }) => {
    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("hsalazar")

    const list = new ECNListPage(page)
    await list.signOut()

    await expect(page).toHaveURL(/login/)
  })

  test("navigating to /ecn while logged out redirects to /login", async ({ page }) => {
    // Fresh page — no auth cookies/tokens
    await page.goto("/ecn")
    await expect(page).toHaveURL(/login/, { timeout: 8_000 })
  })

  test("session persists across page reload", async ({ page }) => {
    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("hsalazar")

    await page.reload()

    // Should still be on /ecn (or redirect back after token refresh)
    await expect(page).toHaveURL(/\/ecn/, { timeout: 8_000 })
  })
})
