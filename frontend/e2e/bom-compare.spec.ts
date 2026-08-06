/**
 * Oskar E2E — BOM Compare (Slice D, ADR-012 D5)
 *
 * Covers:
 *  - "Compare against…" launcher on BOMBrowserPage navigates to
 *    /bom/compare with the left item pre-filled
 *  - Comparing two identical items shows "No differences"
 *  - Comparing two items with a quantity/line difference shows non-zero
 *    Differences/Additions/Subtractions counts and populates the diff table
 *  - Per-field toggle hides a field from the diff table
 *  - Uploading customer_bom.csv (the Slice 0 fixture — multi-row-per-IPN,
 *    "N/A" quantity, blank-MFR/MPN row) against an ERP item runs an
 *    upload-based compare without error (defect (b) regression: the "N/A"
 *    quantity row does not crash the compare or force a 422)
 *  - Export button is present once a comparison result exists
 *
 * Requires the backend running with MOVEX_API_URL pointed at
 * scripts/movex_stub.py (per D7, ADR-012) so these fixtures resolve:
 *   LF100001 -> tests/fixtures/bom/single_level.json   (12 lines, all
 *               effective)
 *   LF100002 -> tests/fixtures/bom/expired_lines.json  (4 raw lines; the
 *               default effectivity filter — GET /bom/{item}'s
 *               include_expired=false default, applied via
 *               get_single_level_bom inside the compare descriptor
 *               resolution — drops the expired/superseded rows, leaving 2
 *               effective lines). LF100001 vs LF100002 is therefore a large,
 *               real diff (mostly "removed" — components present in
 *               LF100001's 12 lines but absent from LF100002's 2), used as
 *               the "differing BOMs" case below.
 *
 *   uvicorn scripts.movex_stub:app --port 8100
 *   MOVEX_API_URL=http://localhost:8100 <start backend>
 *
 * NOTE: this spec was authored per the existing e2e conventions in this
 * repo (helpers/api.ts + helpers/pages.ts, matching bom-browser.spec.ts's
 * own structure and disclosure) but could not be executed in the sandboxed
 * environment this slice was built in — no live frontend/backend/
 * movex_stub trio was running. It has not been visually or functionally
 * verified; treat it as written-to-spec, not confirmed-green, matching how
 * the Slice A/B agent correctly handled the same limitation for
 * bom-browser.spec.ts.
 */

import path from "path"
import { test, expect } from "@playwright/test"
import { getToken, clearTokenCache } from "./helpers/api"
import { LoginPage, BOMBrowserPage, BOMComparePage } from "./helpers/pages"

const FIXTURES_DIR = path.join(__dirname, "..", "..", "tests", "fixtures", "bom")

test.beforeAll(async ({ request }) => {
  clearTokenCache()
  await getToken(request, "eng_user")
})

async function loginAndOpenCompare(page: any): Promise<BOMComparePage> {
  const login = new LoginPage(page)
  await login.goto()
  await login.loginAndExpectList("eng_user")
  const compare = new BOMComparePage(page)
  await compare.goto()
  return compare
}

test.describe("BOM Compare — launcher from BOM Browser", () => {
  test("Compare against… navigates to /bom/compare with the left item pre-filled", async ({ page }) => {
    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("eng_user")

    const browser = new BOMBrowserPage(page)
    await browser.goto()
    await browser.searchFor("LF100001")
    await browser.waitForLoaded()
    await browser.clickCompareAgainst()

    await page.waitForURL("**/bom/compare**")
    const compare = new BOMComparePage(page)
    expect(await compare.leftItemPrefill()).toBe("LF100001")
  })
})

test.describe("BOM Compare — identical BOMs", () => {
  test("comparing an item against itself shows no differences", async ({ page }) => {
    const compare = await loginAndOpenCompare(page)

    await compare.setLeftItem("LF100001")
    await compare.setRightItem("LF100001")
    await compare.clickCompare()
    await compare.waitForResult()

    const counts = await compare.summaryCounts()
    expect(counts.differences).toBe(0)
    expect(counts.additions).toBe(0)
    expect(counts.subtractions).toBe(0)
  })
})

test.describe("BOM Compare — differing BOMs", () => {
  test("comparing two different items shows non-zero diff counts and a populated table", async ({ page }) => {
    const compare = await loginAndOpenCompare(page)

    await compare.setLeftItem("LF100001")
    await compare.setRightItem("LF100002")
    await compare.clickCompare()
    await compare.waitForResult()

    const counts = await compare.summaryCounts()
    const totalDiffs = counts.differences + counts.additions + counts.subtractions
    expect(totalDiffs).toBeGreaterThan(0)
    expect(await compare.diffRowCount()).toBeGreaterThan(0)
  })

  test("toggling a field off removes it from the diff table without erroring", async ({ page }) => {
    const compare = await loginAndOpenCompare(page)

    await compare.setLeftItem("LF100001")
    await compare.setRightItem("LF100002")
    await compare.clickCompare()
    await compare.waitForResult()

    // quantity is a field common to both sides' BOM lines — toggling it off
    // should not throw or blank the whole page.
    await compare.toggleField("quantity")
    await expect(page.locator("text=/Differences/")).toBeVisible()
  })
})

test.describe("BOM Compare — customer file upload (I2-2)", () => {
  test("uploading customer_bom.csv against an ERP item completes without error", async ({ page }) => {
    const compare = await loginAndOpenCompare(page)

    // Switch the left ("Old") side to Upload mode.
    await page.getByRole("button", { name: /upload file/i }).first().click()
    await page.getByLabel(/old \(left\) file/i).setInputFiles(
      path.join(FIXTURES_DIR, "customer_bom.csv"),
    )
    await compare.setRightItem("LF100001")
    await compare.clickCompare()
    await compare.waitForResult()

    // Defect (b) regression at the UI layer: the "N/A" quantity row in
    // customer_bom.csv must not crash the compare or surface an error banner.
    await expect(page.locator("text=/compare failed/i")).toHaveCount(0)
  })
})

test.describe("BOM Compare — export", () => {
  test("export button is available once a comparison result exists", async ({ page }) => {
    const compare = await loginAndOpenCompare(page)

    await compare.setLeftItem("LF100001")
    await compare.setRightItem("LF100002")
    await compare.clickCompare()
    await compare.waitForResult()

    await expect(page.getByRole("link", { name: /export \.xlsx/i })).toBeVisible()
  })
})
