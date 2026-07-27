/**
 * Oskar E2E — MPN Search page (Slice C, ADR-012 D3)
 *
 * Covers:
 *  - /mpn loads with the search form and no results before a search
 *  - Searching a query with no matches shows an empty state
 *  - An MPN that has actually reached the Oskar MPN master (item_mpns) —
 *    i.e. an ECN carrying it was driven all the way to IMPLEMENTED via the
 *    API, exercising the movex_write_complete workflow hook — is findable
 *    via wildcard search and its default badge + lifecycle chips render
 *    correctly in both the results table and the item Sheet drawer.
 *
 * item_mpns only gets populated by the ZECNMPMS migration script or by an
 * ECN reaching movex_write_complete (never directly via UI), so test data
 * setup drives an ECN through the full workflow via API pre-conditions
 * (same ecnAtDCApproved + fireTransition pattern as workflow-full.spec.ts),
 * then only the /mpn page itself is exercised through the UI.
 */

import { test, expect, type APIRequestContext } from "@playwright/test"
import {
  API_BASE,
  getToken,
  clearTokenCache,
  authHeaders,
  ecnAtDCApproved,
  fireTransition,
} from "./helpers/api"
import { LoginPage } from "./helpers/pages"

let engToken: string
let seToken: string
let qmToken: string
let dcToken: string

test.beforeAll(async ({ request }) => {
  clearTokenCache()
  engToken = await getToken(request, "eng_user")
  seToken = await getToken(request, "eng_user") // eng_user doubles as SE, matches workflow-full.spec.ts
  qmToken = await getToken(request, "qm_user")
  dcToken = await getToken(request, "dc_user")
})

// ── Local helper: add an item + MPN, then drive the ECN to IMPLEMENTED ────────
// Not added to helpers/api.ts — kept local to this spec so Slice C's e2e
// additions stay self-contained.

async function addItemAndGetId(
  request: APIRequestContext,
  token: string,
  ecnId: string,
  itemNumber: string,
): Promise<string> {
  const res = await request.post(`${API_BASE}/api/v1/ecn/${ecnId}/items`, {
    headers: authHeaders(token),
    data: {
      item_number: itemNumber,
      item_name: "MPN search e2e part",
      line_number: 10,
      is_new_item: false,
      effectivity_type: "IMMEDIATE",
    },
  })
  if (!res.ok()) throw new Error(`addItem failed: ${res.status()} ${await res.text()}`)
  const body = await res.json()
  return body.id
}

async function addMpn(
  request: APIRequestContext,
  token: string,
  ecnId: string,
  itemId: string,
  mpn: string,
  manufacturer: string,
): Promise<void> {
  const res = await request.post(`${API_BASE}/api/v1/ecn/${ecnId}/items/${itemId}/mpns`, {
    headers: authHeaders(token),
    data: { mpn, manufacturer, is_default: true },
  })
  if (!res.ok()) throw new Error(`addMpn failed: ${res.status()} ${await res.text()}`)
}

/** Builds an ECN with one item + MPN and drives it to IMPLEMENTED, which
 * fires the movex_write_complete workflow hook and upserts item_mpns. */
async function seedImplementedMpn(
  request: APIRequestContext,
  itemNumber: string,
  mpn: string,
  manufacturer: string,
): Promise<void> {
  const { ecnId } = await ecnAtDCApproved(request, engToken, seToken, qmToken)
  const itemId = await addItemAndGetId(request, engToken, ecnId, itemNumber)
  await addMpn(request, engToken, ecnId, itemId, mpn, manufacturer)
  // dc_approve with no routing changes auto-advances straight to IMPLEMENTED
  // (movex_write_complete fires inline — see workflow.py transition()).
  await fireTransition(request, dcToken, ecnId, "dc_approve", "DC")
}

// ─────────────────────────────────────────────────────────────────────────────

test.describe("MPN Search page", () => {
  test("loads with the search form and no results before a search", async ({ page }) => {
    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("hsalazar")

    await page.goto("/mpn")
    await expect(page.getByRole("heading", { name: /mpn search/i })).toBeVisible()
    await expect(page.getByLabel(/mpn search query/i)).toBeVisible()
    await expect(page.getByLabel(/search field/i)).toBeVisible()
  })

  test("searching a query with no matches shows an empty state", async ({ page }) => {
    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("hsalazar")

    await page.goto("/mpn")
    await page.getByLabel(/mpn search query/i).fill("NOPE-DOES-NOT-EXIST-99999*")
    await page.getByRole("button", { name: /search/i }).click()

    await expect(page.getByText(/no mpns found/i)).toBeVisible({ timeout: 8_000 })
  })

  test("a real item_mpns row is findable by wildcard search and shows in the drawer", async ({
    page,
    request,
  }) => {
    const suffix = Date.now().toString().slice(-8)
    const itemNumber = `E2EMPN${suffix}`
    const mpn = `MPNSEARCH${suffix}`
    await seedImplementedMpn(request, itemNumber, mpn, "Murata")

    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("hsalazar")

    await page.goto("/mpn")
    await page.getByLabel(/mpn search query/i).fill(`${mpn.slice(0, -2)}*`)
    await page.getByRole("button", { name: /search/i }).click()

    const row = page.getByRole("row", { name: new RegExp(mpn) })
    await expect(row).toBeVisible({ timeout: 8_000 })
    await expect(row.getByText(/default/i)).toBeVisible()

    await row.click()

    // Sheet drawer opens with default badge + lifecycle ("Current") chip
    await expect(page.getByRole("heading", { name: mpn })).toBeVisible()
    await expect(page.getByText(itemNumber)).toBeVisible()
    await expect(page.locator("text=Current")).toBeVisible()
  })

  test("field selector narrows search to item_number", async ({ page, request }) => {
    const suffix = (Date.now() + 1).toString().slice(-8)
    const itemNumber = `E2EITM${suffix}`
    const mpn = `FIELDSEL${suffix}`
    await seedImplementedMpn(request, itemNumber, mpn, "Yageo")

    const login = new LoginPage(page)
    await login.goto()
    await login.loginAndExpectList("hsalazar")

    await page.goto("/mpn")
    await page.getByLabel(/search field/i).selectOption("item")
    await page.getByLabel(/mpn search query/i).fill(`${itemNumber}*`)
    await page.getByRole("button", { name: /search/i }).click()

    await expect(page.getByRole("row", { name: new RegExp(mpn) })).toBeVisible({ timeout: 8_000 })
  })
})
