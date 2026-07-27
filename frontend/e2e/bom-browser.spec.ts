/**
 * Oskar E2E — BOM Browser (Slice A, ADR-012)
 *
 * Covers:
 *  - Search by item number renders the single-level BOM table
 *  - MSEQ ordering in the rendered table
 *  - Unknown item number shows the "no BOM found" state (404)
 *  - Include-expired toggle changes the visible line count
 *  - Indented tab renders the multi-level explosion tree and supports
 *    expand/collapse of a node
 *  - Where used tab renders the reverse-lookup table for a component
 *
 * Requires the backend to be running with MOVEX_API_URL pointed at
 * scripts/movex_stub.py (per D7, ADR-012) so these fixtures resolve:
 *   LF100001 -> tests/fixtures/bom/single_level.json   (12 lines, all effective)
 *   LF100002 -> tests/fixtures/bom/expired_lines.json  (4 lines, 2 effective)
 *   LF100001 -> tests/fixtures/bom/multi_level.json    (indented, 3 levels)
 *   LF200010 -> tests/fixtures/bom/where_used.json     (2 parent usages)
 *
 *   uvicorn scripts.movex_stub:app --port 8100
 *   MOVEX_API_URL=http://localhost:8100 <start backend>
 *
 * NOTE: this spec was authored per the existing e2e conventions in this repo
 * (helpers/api.ts + helpers/pages.ts) but could not be executed in the
 * sandboxed environment this slice was built in — no live frontend/backend/
 * movex_stub trio was running. It has not been visually or functionally
 * verified; treat it as written-to-spec, not confirmed-green.
 */

import { test, expect } from "@playwright/test"
import { getToken, clearTokenCache } from "./helpers/api"
import { LoginPage, BOMBrowserPage } from "./helpers/pages"

test.beforeAll(async ({ request }) => {
  clearTokenCache()
  await getToken(request, "eng_user")
})

async function loginAndOpenBOM(page: any): Promise<BOMBrowserPage> {
  const login = new LoginPage(page)
  await login.goto()
  await login.loginAndExpectList("eng_user")
  const bom = new BOMBrowserPage(page)
  await bom.goto()
  return bom
}

test.describe("BOM Browser — single-level browse", () => {
  test("searching a known item renders its BOM lines in MSEQ order", async ({ page }) => {
    const bom = await loginAndOpenBOM(page)

    await bom.searchFor("LF100001")
    await bom.waitForLoaded()

    expect(await bom.lineCount()).toBe(12)
    const components = await bom.componentNumbers()
    // single_level.json's first three MSEQ (10/20/30) are LF200010/11/12
    expect(components.slice(0, 3)).toEqual(["LF200010", "LF200011", "LF200012"])
  })

  test("unknown item number shows the not-found state", async ({ page }) => {
    const bom = await loginAndOpenBOM(page)

    await bom.searchFor("NOPE99999")
    await bom.waitForNotFound()
  })

  test("include-expired toggle reveals expired lines", async ({ page }) => {
    const bom = await loginAndOpenBOM(page)

    await bom.searchFor("LF100002")
    await bom.waitForLoaded()
    const defaultCount = await bom.lineCount()

    await bom.toggleIncludeExpired()
    await page.waitForTimeout(500) // let the refetch settle
    const expandedCount = await bom.lineCount()

    expect(expandedCount).toBeGreaterThan(defaultCount)
  })
})

test.describe("BOM Browser — multi-level explosion (Slice B)", () => {
  test("indented tab renders the explosion tree with root and top-level children", async ({ page }) => {
    const bom = await loginAndOpenBOM(page)

    await bom.searchFor("LF100001")
    await bom.waitForLoaded()
    await bom.switchToTab("Indented")
    await bom.waitForTreeLoaded()

    // multi_level.json: root has 3 top-level children by default expansion
    expect(await bom.treeRowCount()).toBeGreaterThanOrEqual(3)
  })

  test("expanding a collapsed node reveals its children", async ({ page }) => {
    const bom = await loginAndOpenBOM(page)

    await bom.searchFor("LF100001")
    await bom.waitForLoaded()
    await bom.switchToTab("Indented")
    await bom.waitForTreeLoaded()

    const before = await bom.treeRowCount()
    // LF300001 (subassembly) starts expanded per BOMTreeView's default depth,
    // but its phantom child LF400001 starts collapsed — expanding it should
    // reveal LF200011/LF200012 underneath.
    await bom.expandTreeNode("LF400001")
    const after = await bom.treeRowCount()

    expect(after).toBeGreaterThan(before)
  })
})

test.describe("BOM Browser — where-used (Slice B)", () => {
  test("where-used tab lists every parent assembly for a component", async ({ page }) => {
    const bom = await loginAndOpenBOM(page)

    await bom.searchFor("LF200010")
    // LF200010 itself has no head fixture, so the Lines tab will 404 —
    // that's fine, where-used is queried independently of the Lines tab.
    await bom.switchToTab("Where used")
    await bom.waitForWhereUsedLoaded()

    const parents = await bom.whereUsedParentItems()
    expect(parents).toEqual(expect.arrayContaining(["LF100001", "LF300001"]))
  })
})
