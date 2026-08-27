# Supplier API Landscape — Component Distributor & Aggregator APIs

**Status:** Research / decision input — not yet an ADR
**Date:** 2026-08-27
**Author:** Research pass for Oskar Iteration 3 (Supplier Intelligence)
**Scope:** Which component-data APIs to integrate next behind `SupplierAdapter`, for an EMS operating in Johor Bahru (MY) and Melbourne (AU).

---

## Evidence standard for this document

Per LL-003, every factual claim about capability, limit, or price below carries a source URL.
Claims I could **not** verify against primary documentation are written as **`unverified`** and must
not be promoted to settled fact without a follow-up check. Several vendors (Mouser, SiliconExpert,
Octopart terms) actively block automated fetching, so some rows are deliberately marked unverified
even where secondary sources agree — see [Verification gaps](#8-verification-gaps) for the exact list.

**A note on what "verified" means here:** it means I read the claim on the vendor's own
documentation or terms page. It does **not** mean the claim was tested against a live API key.
Anything that would change an architecture decision should be confirmed with a real key before build.

---

## 1. The six data needs (restated as the scoring rubric)

| # | Need | Consumer in Oskar |
|---|---|---|
| 1 | MPN → description, manufacturer, category | ECN part-description autofill (live today) |
| 2 | Lifecycle / EOL / obsolescence / last-time-buy | EOL alerting joined to BOM where-used |
| 3 | Price breaks by quantity + stock | BOM scrub cost/risk, quoting |
| 4 | Lead time | Lead-time-spike alerting |
| 5 | Compliance: RoHS, REACH, COO, MSL, packaging, mounting | ECN compliance fields, BOM scrub |
| 6 | Alternate / replacement parts for obsolete parts | EOL remediation workflow |

---

## 2. Comparison table

Legend: ● full · ◐ partial · ○ none · ? unverified

| API | Auth | Rate limit | Free tier | Sandbox | 1 desc | 2 EOL | 3 price/stock | 4 lead | 5 compliance | 6 alts | AU/MY | Caching permitted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **DigiKey PIA v4** | OAuth2 client-credentials | 120/min, 1,000/day; live headers | Yes | Yes, but data is not real | ● | ● | ● | ◐ | ◐ | ◐ | ● AU+MY site & AUD/MYR | **No** — §5.1(e) forbids own DB |
| **Nexar / Octopart** | OAuth2 client-credentials | Part-count quota, not req/s | 100 parts **lifetime** | No | ● | ◐ Pro+ only | ● | ● | ? | ◐ Pro+ "Similar Parts" | ◐ global aggregate | **No** — 24h cache limit (dated source) |
| **Element14 / Farnell / Newark** | API key (query param) | Undisclosed; "courtesy allowance" | Yes | ? | ● | ◐ `productStatus` | ● `prices` from/to/cost | ● `leastLeadTime` | ◐ `rohsStatusCode`, `countryOfOrigin` | ○ | ● **au** + **my** storefronts | **No** — near-identical anti-cache clause |
| **Mouser Search API** | API key | 1,000/day (unverified) | Yes | ? | ● | ? | ● | ? | ? | ○ | ◐ no MY/AU store | **No** (unverified wording) |
| **Arrow P&A v4** | login + apikey in URI | **No documented limit** | Yes | ? | ● | ? | ● 100 parts/call | ? | ? | ○ | ? | **No** — explicitly stated |
| **TME** | Token + HMAC signature | **5 req/s** | Yes, anonymous token | Yes | ● | ? | ● | ● delivery time | ? | ○ | ○ EU-centric | ? |
| **Avnet** | Subscription key **+** OAuth2 | ? | Approval-gated | Not mentioned | ● | ? | ● | ? | ? | ○ | ? | ? |
| **LCSC** | ? | ? (exists, undisclosed) | Application form + approval | ? | ● | ? | ● | ? | ? | ○ | ◐ China/APAC ship | ? |
| **Future Electronics** | API key, approval-gated | ? | Approval-gated | ? | ● | ? | ● | ? | ? | ○ | ? | ? |
| **RS Components** | — | — | **No public API** | — | ○ | ○ | ○ | ○ | ○ | ○ | — | — |
| **SiliconExpert** | ? (403 on docs) | Per-part quota | No | ? | ● | ● YTEOL, LTB, PCN | ◐ | ? | ● RoHS/REACH | ● | ? | ? |
| **Z2Data** | API key + RBAC | "enterprise volume" | Free trial only | ? | ● | ● PCN/NRND/LTB webhooks | ● | ? | ● RoHS/REACH/PFAS/TSCA | ● | ? | ? |
| **Accuris (IHS/S&P)** | ? | ? | No | ? | ● | ● | ? | ? | ● | ● | ? | ? |
| **Supplyframe / Findchips** | — | — | — | — | — | — | — | — | — | — | — | dev portal **DNS does not resolve** |
| **Altium 365 / CSE** | — | ECAD models, not supply data | Free models | — | ◐ | ○ | ○ | ○ | ○ | ○ | — | out of scope |

---

## 3. The finding that matters most: caching is contractually prohibited nearly everywhere

This is the single most consequential result of this research, and it is an architectural problem,
not a licensing footnote. Oskar's `SupplierChain` caches responses in `supplier_part_cache` for
**30 days** (`SUPPLIER_CACHE_TTL_DAYS`, default 30). Read literally, that violates the terms of
**every major distributor API examined**:

- **DigiKey** — the User Agreement §5.1(e) prohibits using the API or DigiKey Data "to update or
  create your own database of information", §5.1(d) prohibits bulk download, and §3.2(iv) prohibits
  distributing data to third parties other than displaying it on Your Site or Internal Application.
  ([api-user-agreement](https://developer.digikey.com/api-user-agreement))
- **Element14/Farnell** — "cache, record, pre-fetch, or otherwise store any portion of the Farnell
  Content" and "use it to update or create your own database of business listing information".
  ([partner.element14.com/terms](https://partner.element14.com/terms))
- **Arrow** — "Data caching violates the API Terms of Use and results in credential revocation."
  ([Best Practices](https://developers.arrow.com/api/index.php/site/page?view=bestPractices))
- **Mouser** — reported as "cache, record, pre-fetch, or otherwise store any portion of the Mouser
  Electronics Content… or use it to update or create your own database". **`unverified`** — the
  terms page timed out repeatedly; wording corroborated only by two independent search summaries.
  ([mouser.com/en/apiterms](https://www.mouser.com/en/apiterms/))
- **Octopart/Nexar** — "You will not maintain any cached data retrieved using the Octopart API for a
  period longer than 24 hours." **`unverified as current`** — [octopart.com/api/terms](https://octopart.com/api/terms)
  returns HTTP 403 to automated fetch. The one substantive clarification found is a **2014** Octopart
  staff post saying the 24h rule was aimed at "proprietary pieces of data like datasheets, images,
  reference designs" and that an internal SQL database of part definitions and pricing refreshed via
  the API "is precisely what we…would like to support"
  ([groups.google.com thread, May 2014](https://groups.google.com/g/octopart-api/c/3Aw1O3A4_iY)).
  That post predates the Altium acquisition and the Nexar migration and **must not be relied on**.

Note the near-identical phrasing between Mouser and Element14 — this is shared industry boilerplate,
which is why it recurs. Its practical enforcement is unknown, but it is uniform enough that
"nobody actually enforces this" is a bet, not a finding.

### What to do about it — three options, not a recommendation

I am flagging this rather than resolving it, because it is a commercial/legal call, not a technical one.

1. **Ask, don't assume.** Every one of these terms invites contact for variance (Element14: "contact
   us and we can discuss your particular situation"; Mouser reportedly the same). An EMS with real
   purchasing volume is exactly the counterparty that gets a written variance. **This is the
   recommended path** and should start before Iteration 3 build, since the answer changes the design.
2. **Shorten the TTL and split the cache by field class.** The 2014 Octopart clarification, even
   dated, points at a real distinction: *descriptive* data (MPN, manufacturer, category, mounting
   type) is low-risk and slow-changing; *commercial* data (price, stock) is what the terms actually
   protect. A schema that caches descriptive fields for 30 days and price/stock for ≤24h is far more
   defensible and is also simply more correct — 30-day-old pricing is wrong data regardless of terms.
3. **Push commercial data to an aggregator with a negotiated contract**, where caching rights are an
   explicit term rather than an inherited boilerplate prohibition.

**Concrete consequence for the Iteration 3 schema change:** the planned move of the cache PK to
`(supplier_id, mpn)` with price-breaks and stock columns should carry a **per-field-class TTL**, not
one global `SUPPLIER_CACHE_TTL_DAYS`. Adding price/stock columns under a single 30-day TTL makes the
current terms exposure materially worse, because it moves precisely the protected data into the
persistent store. Recommend a `cached_at` per class or a separate `supplier_part_price_cache` table.

---

## 4. Recommendation: which 3–4 to implement next, in order

### #1 — Element14 / Farnell / Newark ⭐ strongest single addition

**Why first:** it is the only candidate that scores on needs **3, 4 and 5 simultaneously** with a
free, self-service API key, *and* has native Malaysian and Australian storefronts.

- `storeInfo.id` explicitly includes **`my.element14.com`** and **`au.element14.com`** (also `sg`,
  `nz`, `th`, `ph`, `in`) — verified in the
  [storeInfo.id values list](https://partner.element14.com/search_api/storeInfoid_Values). No other
  API examined offers per-country storefront selection matching Scanfil's two sites this directly.
- Returns `prices` with `cost`/`from`/`to` (real price breaks — need 3), `stock` with `level` and
  **`leastLeadTime`** (need 4 — the only free API found that returns lead time as a first-class
  field), plus `rohsStatusCode`, `countryOfOrigin`, `packSize` and `productStatus`
  (`NO_LONGER_MANUFACTURED` is a usable EOL signal for need 2). All verified in the
  [REST API Description](https://partner.element14.com/docs/read/Product_Search_API_REST__Description).
- Auth is a plain 24-character API key — cheapest possible adapter, no OAuth token lifecycle.

**Caveats:** rate limits are **not published** ("courtesy usage allowance", contact for more) — so
the DigiKey live-header quota pattern **cannot** be reused; budget for blind 429 handling instead.
Currency per store is *not* documented and must be confirmed empirically. Sandbox existence
`unverified`.

### #2 — Nexar, upgraded from free tier

Nexar is already implemented — but the adapter's docstring is **wrong**, and that is a live bug, not
a research note. Fixing it is cheaper than any new adapter.

> `nexar.py` states "Free tier — 100 matched parts/month". Nexar documents the evaluation app as a
> **lifetime** limit of 100 that **"will not reset each month"**
> ([Part Limits](https://support.nexar.com/support/solutions/articles/101000476314-part-limits-and-how-they-work)).

The practical effect: the Nexar fallback in `SupplierChain` is almost certainly **already exhausted
and silently failing** — and because `chain.get_part()` catches every exception and continues, that
failure is invisible. Two actions: correct the docstring, and decide whether to pay.

Also note **quota is per matched part, not per request** — a `search()` call with `limit=20` costs
20 parts, not 1. The existing `search()` method is a quota bomb at default limit.

Lifecycle status and "Similar Parts" (needs 2 and 6) are **Pro tier and above**, not Standard —
verified on [compare-plans](https://nexar.com/compare-plans). Pricing for Standard/Pro is **not
published** (`unverified`); the $100/month figure in the adapter docstring is uncited and should be
treated as stale until re-quoted.

Nexar exposes quota via a `supplyCounts` GraphQL query (`partCounter`/`partLimit`), **not** response
headers — so quota tracking needs a polled query, not the DigiKey header pattern.

### #3 — TME

Best-documented small-vendor API found, and the only one with a **published, hard rate limit**:
**5 enquiries per second** ([TME terms](https://developers.tme.eu/pdfs/en/terms.pdf), per search
extract — PDF returned 404 on direct fetch, so `unverified` at source). Free anonymous tokens,
sandbox available, returns stock/prices/parameters/delivery time
([developers.tme.eu](https://developers.tme.eu/en/)). HMAC-signed requests make it the most
expensive adapter to write of the three.

**Honest caveat:** TME is EU-centric. Its value to Johor Bahru and Melbourne operations is
**questionable** and it should be third precisely because of that. If Iteration 3 has budget for
only two adapters, **stop after #2** and spend the remainder on the aggregator question in §5.

### #4 — conditional: a paid obsolescence source (SiliconExpert or Z2Data)

Only if need 2 (EOL alerting) and need 6 (alternates) are genuinely in Iteration 3 scope. See §5 and §6.

### Explicitly deprioritised

- **Arrow** — the only vendor that states caching violates terms *and* revokes credentials for it.
  Also has **no documented rate limit at all**, which is worse than a low one: nothing to design
  against, and "abuse will result in revocation of credentials"
  ([Best Practices](https://developers.arrow.com/api/index.php/site/page?view=bestPractices)).
  Building a cache-backed adapter against Arrow is building a credential-revocation risk.
- **Avnet** — dual auth (subscription key **and** OAuth2 client-credentials), approval-gated, no
  sandbox mentioned ([How To](https://apiportal.avnet.com/help/HowTo)). Highest integration cost of
  the distributor set for no differentiated data.
- **LCSC / Future Electronics** — both approval-gated with undisclosed limits and no public field
  documentation. Not evaluable without applying first. LCSC may deserve a second look purely on
  Johor Bahru proximity and cost, but that is a sourcing decision, not a data decision.

---

## 5. On the currently-stubbed names — say it plainly

`stubs.py` names **Mouser, RS Components, Arrow, Avnet, Future6**. Three of the four named suppliers
are poor choices, and one is impossible.

| Stub | Verdict |
|---|---|
| **RS Components** | **Delete the stub — it cannot be implemented.** No public product API, no developer portal, no self-service key. RS offers account-gated eProcurement (PunchOut via OCI/cXML), which is a procurement transport, not a part-data API. **`unverified`** — this rests on secondary sources plus the absence of any RS developer portal in searches; RS publishes no page saying "we have no API", so this is an argument from absence. Confirm with the RS account manager before deleting, but do not plan Iteration 3 around it. |
| **Arrow** | **Poor choice for this use case.** Not on capability — on terms. Explicit anti-caching + credential revocation + no documented rate limit is the worst possible combination for a cache-backed platform. |
| **Avnet** | **Poor cost/benefit.** Most complex auth of the set, approval-gated, no sandbox, no unique data. |
| **Mouser** | **Defensible but not the best next step.** Good catalogue and a genuine free API key, but no MY/AU storefront, reportedly the most restrictive caching language, and I could not verify a single claim against its own site — every Mouser page timed out. Lower value than Element14 on every axis that matters here. |
| **Future6** | Placeholder. **Recommend renaming to `Element14Adapter`** as the first Iteration 3 implementation. |

**Net:** the stub list encodes a set of assumptions from PRE-5 that this research does not support.
The four named distributors were plausibly chosen for brand recognition in the EMS space rather than
for API suitability. Element14 — which is *not* in the stub list — is the strongest candidate found.

---

## 6. Aggregator vs. direct distributor

### The maintenance-burden argument is real, and it favours the aggregator

Each direct adapter is not a one-off cost. It is: an auth scheme (OAuth2 / HMAC / key-in-URI — all
three appear above), a distinct rate-limit model (header-reported, part-counted, per-second, or
undocumented), a bespoke response shape to normalise, a separate ToS exposure, and an ongoing
breakage surface. `digikey.py` is the proof: it carries a hand-rolled pybreaker async driver, a
percent-encoding fix for MPNs containing `/`, and a GET→POST correction for the v4 keyword endpoint
that was live-verified on 2026-08-19 — and `search()` was **broken from the start and nobody
noticed**, because it had no production callers. That is one adapter's worth of accumulated
sharp edges. Multiply by four.

Against that: **one aggregator adapter, one auth, one normalisation, one contract.**

### But the aggregators split into two different products, and the distinction is the whole decision

**Nexar/Octopart is a *supply* aggregator.** It answers "who has it, how much, how many." It
aggregates the distributors — so it substitutes for building Mouser + Arrow + Avnet + Future
adapters. It is weak on exactly what Oskar's highest-value features need: lifecycle is Pro-tier,
alternates are "Similar Parts" at Pro-tier, and there is no PCN/last-time-buy feed at all.

**SiliconExpert / Z2Data / Accuris are *risk* aggregators.** They answer "is this part dying, is it
compliant, what replaces it." Z2Data's API documents lifecycle stage, compliance status, supplier
risk, country-of-origin, and — critically — **webhooks that fire on PCN issuance, NRND transition,
and last-time-buy notices**, described as event-push "with no polling"
([Z2Data API](https://www.z2data.com/products/part-risk-manager/features/api-access-integration/)).
SiliconExpert similarly advertises Estimated YTEOL, EOL Date, Last Time Buy, Last PCN and GIDEP
([SiliconExpert API](https://www.siliconexpert.com/products/api/) — page returns 403 to automated
fetch, so `unverified` at source).

**These are not substitutes for each other, and neither is a substitute for a distributor API.**

### Recommendation

Do **not** buy an aggregator to replace direct adapters — buy one to get data no distributor sells.

- **Replace the four remaining stubs with Nexar** (upgraded tier) rather than building them. That is
  where the maintenance-burden argument wins outright: four adapters, four ToS, four rate-limit
  models collapse into one already-written adapter needing only a plan change.
- **Add Element14 directly anyway**, because it is free, it is the only good AU/MY regional signal,
  and it returns lead time — which is a real gap in the aggregator's cheap tiers.
- **Treat a risk aggregator as a separate, later, budgeted decision** tied to whether EOL alerting
  (need 2) and alternates (need 6) are actually being built. It is not an Iteration 3 impulse buy.

**Cost anchor — treat as indicative only:** SiliconExpert annual subscriptions for small-to-mid
companies are reported at roughly **$5K–$15K/year**. This figure comes from a search summary, not
from SiliconExpert, whose pricing is unpublished. **`unverified`** — get a written quote.

---

## 7. Which of the six needs NO free/cheap API covers well

This is the section to read before planning, so these are known now rather than discovered mid-build.

| Need | Free-tier reality |
|---|---|
| **1 — description/manufacturer/category** | ✅ **Well covered.** Every API does this. Already working via DigiKey. No further spend needed. |
| **3 — price breaks + stock** | ✅ **Well covered.** DigiKey, Element14, Nexar, TME, Arrow all return it. The constraint is *caching terms* (§3), not availability. |
| **4 — lead time** | ⚠️ **Thin.** Element14's `leastLeadTime` and TME's delivery time are the only free first-class lead-time fields found. Nexar includes Lead Time at all tiers. DigiKey's v4 product detail exposes no lead-time field in the shape `digikey.py` currently parses. **Lead-time-spike alerting effectively depends on adding Element14.** |
| **2 — lifecycle / EOL / LTB** | ❌ **Genuine gap.** Free APIs give a *status string* — DigiKey `ProductStatus.Status`, Element14 `productStatus: NO_LONGER_MANUFACTURED`. That is a **lagging** indicator: it tells you the part is already dead. It is **not** last-time-buy dates, **not** PCN/PDN feeds, **not** EOL forecasting. Nexar puts even the status string behind Pro tier. Real obsolescence data (YTEOL, LTB dates, PCN feeds, GIDEP) exists only in paid risk aggregators. **Do not scope predictive EOL alerting against free APIs — it cannot be built.** A "part is already obsolete" alert *can* be. |
| **5 — compliance attributes** | ⚠️ **Partial, and unevenly.** RoHS and country-of-origin are reachable free (Element14 `rohsStatusCode`, `countryOfOrigin`; DigiKey via `Parameters[]`). **REACH, MSL level, and packaging are not reliably available from any free API examined.** `digikey.py` already demonstrates the shape of the problem: `_extract_mounting_type()` scrapes free-text `ParameterText`/`ValueText` pairs and normalises with substring hints. That approach works, but it is inference from unstructured strings, not a structured field — expect the same or worse for MSL and packaging. Budget for manual entry or a paid source. |
| **6 — alternates / replacements** | ❌ **Genuine gap.** Nothing free. Nexar "Similar Parts" is Pro-tier and is *parametric similarity*, which is not the same as a manufacturer-sanctioned replacement. Validated cross-references are a paid-aggregator feature. |

**Summary for planning:** needs **1 and 3** are solved. Need **4** is solved *if* Element14 is added.
Needs **2 and 6** are **not achievable on free tiers** and need either budget or descoping — this is
the key planning input. Need **5** is partially achievable with per-attribute string parsing.

---

## 8. Verification gaps

Explicitly unverified. Each needs a primary-source check or a live API key before being treated as fact.

| Claim | Why unverified |
|---|---|
| Mouser 1,000 calls/day, 30 calls/min, 50 parts/call | Every `mouser.com` fetch timed out. Search-summary only. |
| Mouser anti-caching clause wording | Terms page unreachable; two independent search summaries agree, source not read directly. |
| Octopart 24h caching clause **is current** | [octopart.com/api/terms](https://octopart.com/api/terms) and the Octopart API FAQ both return HTTP 403. Only substantive clarification found is from **2014**, pre-Altium. |
| Nexar Standard/Pro pricing | Not published on [compare-plans](https://nexar.com/compare-plans). The `$100/month` in `nexar.py` is uncited and possibly stale. |
| SiliconExpert capabilities and $5K–$15K/yr | [Product page](https://www.siliconexpert.com/products/api/) returns 403. Search-summary only. |
| Element14 rate limits | Not published anywhere found — only "courtesy usage allowance". |
| Element14 currency per storefront | Not documented; confirm empirically per `storeInfo.id`. |
| Element14 / Mouser / Arrow / Avnet / LCSC / Future sandbox existence | Not stated in any doc found. |
| TME 5 req/s | [terms.pdf](https://developers.tme.eu/pdfs/en/terms.pdf) returned 404 on direct fetch; figure from search extract of that document. |
| RS Components has no public API | Argument from absence + secondary sources. Confirm with RS account manager. |
| Avnet / LCSC / Future / Z2Data rate limits and pricing | All approval-gated or unpublished. |
| Supplyframe/Findchips API status | `dev.supplyframe.com` **DNS does not resolve** (`ENOTFOUND`). Treat the public dev programme as defunct absent contrary evidence. |
| Accuris (IHS/S&P) API specifics | Enterprise sales-gated; no public API documentation found. |

---

## 9. Codebase corrections this research surfaced

Not part of the research brief, but found while reading context — flagged, **not actioned** (this
pass modified no file but this one).

1. **`nexar.py` docstring is factually wrong.** "Free tier — 100 matched parts/month" — Nexar
   documents 100 parts **lifetime, non-resetting**. Implication: the Nexar fallback is likely already
   dead in any environment that has used it, and `chain.py` swallows the failure silently.
2. **`nexar.py` `$100/month` for Standard is uncited** and unverifiable against current published
   pricing.
3. **`nexar.py` comment "Nexar does not surface lifecycle status in free tier"** is right for the
   wrong reason — lifecycle is gated to **Pro and above**, not merely absent from free.
4. **`NexarAdapter.search()` costs `limit` parts per call, not one.** At `limit=20` default, a single
   search consumes a fifth of the entire lifetime evaluation quota.
5. **Cache TTL should not stay a single global value** once price/stock columns land in the
   Iteration 3 schema change — see §3.
6. **`base.py` docstring** lists the six original suppliers; if Element14 replaces `Future6`, update
   it alongside `stubs.py`.

---

## Sources

- [DigiKey API User Agreement](https://developer.digikey.com/api-user-agreement)
- [DigiKey Shared Concepts — rate limit headers](https://developer.digikey.com/tutorials-and-resources/shared-concepts)
- [DigiKey Developer FAQ — sandbox behaviour, keyword-search staleness](https://developer.digikey.com/faq)
- [Nexar — Part Limits and How They Work](https://support.nexar.com/support/solutions/articles/101000476314-part-limits-and-how-they-work)
- [Nexar — Compare Plans](https://nexar.com/compare-plans)
- [Nexar — FAQ](https://support.nexar.com/support/solutions/articles/101000497890-frequently-asked-questions)
- [Octopart API terms-of-use clarification thread, May 2014](https://groups.google.com/g/octopart-api/c/3Aw1O3A4_iY)
- [element14 — storeInfo.id values](https://partner.element14.com/search_api/storeInfoid_Values)
- [element14 — Product Search API (REST) Description](https://partner.element14.com/docs/read/Product_Search_API_REST__Description)
- [element14 — Product Search API Characteristics](https://partner.element14.com/docs/read/Product_Search_API_REST_Characteristics)
- [element14 — Terms of Use](https://partner.element14.com/terms)
- [Arrow — Best Practices (caching prohibition, no rate limits)](https://developers.arrow.com/api/index.php/site/page?view=bestPractices)
- [Arrow — Getting Started (auth)](https://developers.arrow.com/api/index.php/site/page?view=gettingStarted)
- [Mouser — Search API](https://www.mouser.com/en/api-search/) *(unreachable — see §8)*
- [Mouser — API Terms of Use](https://www.mouser.com/en/apiterms/) *(unreachable — see §8)*
- [TME — Developers portal](https://developers.tme.eu/en/)
- [TME — Terms and Conditions PDF](https://developers.tme.eu/pdfs/en/terms.pdf) *(404 on direct fetch)*
- [Avnet API Portal — How To](https://apiportal.avnet.com/help/HowTo)
- [Avnet API Portal](https://apiportal.avnet.com/)
- [LCSC — API FAQs](https://www.lcsc.com/faqs/api)
- [LCSC — Open API docs](https://www.lcsc.com/docs/openapi/index.html)
- [Future Electronics — API Solutions](https://www.futureelectronics.com/api-solutions)
- [Z2Data — API Access & Integration](https://www.z2data.com/products/part-risk-manager/features/api-access-integration/)
- [SiliconExpert — API](https://www.siliconexpert.com/products/api/) *(403 — see §8)*
- [Accuris — Parts Intelligence](https://accuristech.com/solutions/parts-intelligence/)
- [Octopart — API terms](https://octopart.com/api/terms) *(403 — see §8)*
