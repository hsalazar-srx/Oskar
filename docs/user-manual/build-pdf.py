#!/usr/bin/env python3
"""Build the Oskar user manual as a single PDF.

    python docs/user-manual/build-pdf.py

Markdown -> HTML (Python-Markdown) -> PDF (headless Chromium via Playwright).

Engine choice: Prince is installed on this machine and renders this beautifully,
but only under a **non-commercial licence** — it stamps a watermark on every
page, and this is a commercial manual for Scanfil APAC staff, so using it here
would be outside its terms. WeasyPrint needs GTK/Pango native libraries that are
not present on Windows. Chromium is already available (Playwright, installed for
frontend screenshot checks), is licence-clean, and supports the CSS paged-media
features this manual needs.

The one thing Chromium lacks is `target-counter()`, so a contents page cannot
resolve its own page numbers during layout. This builds in two passes instead:
render once, read where each chapter actually landed, then re-render with those
numbers injected. See build_pdf().

Versioning
----------
Bump MANUAL_VERSION and add a REVISIONS entry whenever the manual is reissued;
set STATUS to "Approved" once it has been signed off. The build stamps the git
commit and date automatically, so any printed copy can be traced back to the
exact code state its screenshots and behaviour describe — which matters here
because the manual documents live UI.

Design notes worth knowing before editing:

  * Chapter order comes from CHAPTERS below, not from a glob, so 05a sorts
    after 05 and the reading order matches README.md's table.
  * Inter-chapter links (`04-approving-an-ecn.md#section`) are rewritten to
    in-document anchors, so cross-references keep working inside one PDF.
    Anchors are namespaced per chapter (`ch04--section`) because several
    chapters use the same heading text and would otherwise collide.
  * Screenshots vary from 1440x700 to 1440x2668. A tall one at full width
    overflows the text block and pushes captions onto their own page, so
    images are capped by height as well as width.
  * `>` blockquotes are the manual's callout convention throughout, so they
    are styled as callouts rather than as quotations.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import markdown

# ── Document control ───────────────────────────────────────────────────────
MANUAL_VERSION = "1.0"
STATUS = "Draft"          # Draft | For Review | Approved
OWNER = "Lead Engineer, Development & Integration"

# Newest first. Keep entries short — this is a reader-facing change log, not a
# commit log.
REVISIONS: list[tuple[str, str, str]] = [
    ("1.0", "August 2026", "First issue. Covers ECN creation, approval, the DC gate, "
                           "BOM tools, bulk uploads and onboarding. Includes BOM-only "
                           "ECNs (ADR-014)."),
]

HERE = Path(__file__).parent
# Chromium comes from the frontend's dev dependency, already installed for the
# screenshot checks — no second browser download for the docs build.
FRONTEND = HERE.parent.parent / "frontend"
OUT_HTML = HERE / "oskar-user-manual.html"
OUT_PDF = HERE / "oskar-user-manual.pdf"

# Explicit order — mirrors README.md's "All chapters" table. README itself is
# not included as a chapter: its job (who reads what) is covered by the
# front-matter reading-paths page, and its chapter table is replaced by the
# generated contents.
CHAPTERS: list[tuple[str, str]] = [
    ("01-getting-started.md", "Getting started"),
    ("02-glossary.md", "Glossary and reference"),
    ("03-raising-an-ecn.md", "Raising an ECN"),
    ("04-approving-an-ecn.md", "Approving an ECN"),
    ("05-document-controller.md", "The Document Controller"),
    ("05a-admin.md", "Admin"),
    ("06-bom-tools.md", "BOM tools"),
    ("07-bulk-uploads.md", "Bulk uploads"),
    ("08-notifications.md", "Notifications"),
    ("09-finding-ecns.md", "Finding ECNs"),
    ("10-troubleshooting.md", "When things go wrong"),
    ("11-coming-from-stargile.md", "Coming from Stargile"),
    ("12-access-and-onboarding.md", "Access and onboarding"),
]

MD_EXTENSIONS = ["tables", "fenced_code", "attr_list", "sane_lists", "toc"]


def git_describe() -> tuple[str, str]:
    """(short sha, 'clean'|'modified'). Empty sha if git is unavailable."""
    def run(*args: str) -> str:
        try:
            return subprocess.run(args, cwd=HERE, capture_output=True,
                                  text=True, timeout=15).stdout.strip()
        except Exception:  # noqa: BLE001 — git absence must not fail the build
            return ""
    sha = run("git", "rev-parse", "--short", "HEAD")
    dirty = run("git", "status", "--porcelain")
    return sha, ("modified" if dirty else "clean")


def chapter_id(filename: str) -> str:
    """`05a-admin.md` -> `ch05a`. Used to namespace per-chapter anchors."""
    return "ch" + filename.split("-")[0]


def slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_]+", "-", text).strip("-")


def rewrite_links(html_text: str, this_chapter: str) -> str:
    """Point cross-chapter links at in-document anchors.

    `href="04-approving-an-ecn.md#the-gate"` -> `href="#ch04--the-gate"`
    `href="#the-gate"`                       -> `href="#chNN--the-gate"`

    Links to templates/ and any external URL are left alone — the templates
    are shipped alongside the PDF, not embedded in it.
    """
    def repl_cross(m: re.Match[str]) -> str:
        target, frag = m.group(1), m.group(2)
        cid = chapter_id(target)
        return f'href="#{cid}--{frag}"' if frag else f'href="#{cid}"'

    html_text = re.sub(r'href="([0-9]{2}[0-9a-z]*-[^"#]+\.md)(?:#([^"]+))?"',
                       repl_cross, html_text)
    # Same-chapter fragment links need the chapter prefix too.
    html_text = re.sub(r'href="#([^"]+)"',
                       lambda m: f'href="#{this_chapter}--{m.group(1)}"'
                       if not m.group(1).startswith("ch") else m.group(0),
                       html_text)
    return html_text


def namespace_headings(html_text: str, cid: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Prefix every heading id with the chapter, and collect the TOC entries."""
    entries: list[tuple[int, str, str]] = []

    def repl(m: re.Match[str]) -> str:
        level, attrs, text = int(m.group(1)), m.group(2), m.group(3)
        existing = re.search(r'id="([^"]+)"', attrs)
        slug = existing.group(1) if existing else slugify(text)
        new_id = f"{cid}--{slug}"
        if level <= 2:
            entries.append((level, new_id, re.sub(r"<[^>]+>", "", text)))
        attrs = re.sub(r'\s*id="[^"]+"', "", attrs)
        return f'<h{level} id="{new_id}"{attrs}>{text}</h{level}>'

    html_text = re.sub(r"<h([1-6])([^>]*)>(.*?)</h\1>", repl, html_text, flags=re.S)
    return html_text, entries


def css(status_footer: str, part: str = "all") -> str:
    # A non-approved manual carries its status in the page footer as well as on
    # the cover, so a page photocopied out of context still says what it is.

    # The cover is a full-bleed dark page and the body is not, so the page
    # margin is set per document rather than overridden with `@page :first`.
    #
    # That override is what broke "About this manual": the cover renders as its
    # own document, so in the body document `:first` matched the front matter
    # instead, printing it edge to edge with its H1 under the running header.
    if part == "cover":
        page_margin = "0"
        margin_note = "/* Cover bleeds to the paper edge; no running furniture. */"
    else:
        page_margin = "20mm 18mm 18mm 18mm"
        margin_note = (
            "/* Room for Chromium's header/footer templates, which Playwright\n"
            "     supplies because Chromium has no @page margin boxes. 20mm top\n"
            "     clears the header band; at 16mm it collided with each H1. */"
        )

    return f"""
@page {{
  size: A4;
  {margin_note}
  margin: {page_margin};
}}

html {{ font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
       font-size: 10.2pt; line-height: 1.55; color: #1e293b; }}
body {{ margin: 0; }}

/* ── Cover ─────────────────────────────────────────────────────────────── */
/* 100vh, not a hard 297mm: with zero page margins Chromium's printable box is
   very slightly under a full A4 sheet, and 297mm overflowed onto a second
   blank page while shrinking the visible panel. `page: cover` is a Prince
   named-page reference Chromium ignores; harmless, kept out. */
.cover {{ height: 100vh; position: relative; overflow: hidden;
         background: #0f172a; color: #fff; }}
.cover-inner {{ position: absolute; top: 62mm; left: 22mm; right: 22mm; }}
.cover .mark {{ width: 15mm; height: 15mm; border-radius: 3mm; background: #0066cc;
               color: #fff; font-weight: 700; font-size: 20pt; text-align: center;
               line-height: 15mm; margin-bottom: 12mm; }}
.cover h1 {{ font-size: 34pt; margin: 0 0 3mm; font-weight: 600; letter-spacing: -0.5pt;
            color: #fff; border: 0; padding: 0; }}
.cover .sub {{ font-size: 13pt; color: #94a3b8; margin: 0 0 14mm; font-weight: 300; }}
.cover .badge {{ display: inline-block; padding: 1.6mm 4mm; border-radius: 1.5mm;
                font-size: 10pt; font-weight: 600; letter-spacing: 0.6pt;
                text-transform: uppercase; margin-bottom: 16mm;
                background: #f59e0b; color: #78350f; }}
.cover .badge.approved {{ background: #10b981; color: #064e3b; }}
.cover .meta {{ font-size: 9.5pt; color: #64748b; line-height: 1.9; }}
.cover .meta strong {{ color: #cbd5e1; font-weight: 500; }}
.cover .docref {{ position: absolute; bottom: 20mm; left: 22mm; right: 22mm;
                 font-size: 8pt; color: #475569; border-top: 0.5pt solid #1e293b;
                 padding-top: 4mm; }}

/* ── Front matter ──────────────────────────────────────────────────────── */
/* `page: frontmatter` was a Prince named-page reference; Chromium has no
   named pages, and there is no matching @page rule any more. */
.frontmatter {{ page-break-after: always; }}
.doc-control td:first-child {{ width: 34mm; color: #64748b; }}
.status-note {{ background: #fffbeb; border-left: 2.5pt solid #f59e0b;
               padding: 3mm 4mm; border-radius: 0 1mm 1mm 0; margin: 0 0 5mm; }}
.status-note p {{ margin: 0; font-size: 9.6pt; color: #78350f; }}

/* ── Contents ──────────────────────────────────────────────────────────── */
.toc h1 {{ border: 0; }}
.toc ol {{ list-style: none; padding: 0; margin: 0; }}
.toc li {{ margin: 0; }}
.toc a {{ text-decoration: none; color: #1e293b; display: block;
         border-bottom: 0.4pt dotted #cbd5e1; padding: 1.6mm 0 1.2mm; }}
.toc a::after {{ content: attr(data-page); float: right;
                color: #64748b; font-size: 9pt; }}
.toc .lvl1 > a {{ font-weight: 600; margin-top: 3mm; }}
.toc .lvl2 > a {{ padding-left: 7mm; font-size: 9.2pt; color: #475569; border-bottom: 0; }}
.toc .lvl2 > a::after {{ font-size: 8.5pt; }}

/* ── Chapters ──────────────────────────────────────────────────────────── */
.chapter {{ page-break-before: always; }}

h1 {{ font-size: 20pt; font-weight: 600; color: #0f172a; margin: 0 0 6mm;
     padding-bottom: 3mm; border-bottom: 1.6pt solid #0066cc; letter-spacing: -0.3pt; }}
h2 {{ font-size: 13.5pt; font-weight: 600; color: #0f172a; margin: 9mm 0 3mm;
     page-break-after: avoid; }}
h3 {{ font-size: 11.2pt; font-weight: 600; color: #334155; margin: 6mm 0 2mm;
     page-break-after: avoid; }}
h4 {{ font-size: 10.2pt; font-weight: 600; color: #475569; margin: 5mm 0 1.5mm;
     page-break-after: avoid; }}
p {{ margin: 0 0 3mm; orphans: 3; widows: 3; }}
ul, ol {{ margin: 0 0 3.5mm; padding-left: 6mm; }}
li {{ margin-bottom: 1.2mm; }}
strong {{ color: #0f172a; font-weight: 600; }}
a {{ color: #0066cc; text-decoration: none; }}
hr {{ border: 0; border-top: 0.5pt solid #e2e8f0; margin: 7mm 0; }}

/* ── Tables ────────────────────────────────────────────────────────────── */
table {{ width: 100%; border-collapse: collapse; margin: 0 0 5mm;
        font-size: 9.2pt; page-break-inside: avoid; }}
thead {{ background: #f1f5f9; }}
th {{ text-align: left; font-weight: 600; color: #0f172a; padding: 2mm 2.5mm;
     border-bottom: 1pt solid #cbd5e1; }}
td {{ padding: 1.8mm 2.5mm; border-bottom: 0.4pt solid #e2e8f0; vertical-align: top; }}
tr {{ page-break-inside: avoid; }}

/* ── Code ──────────────────────────────────────────────────────────────── */
code {{ font-family: 'Cascadia Mono', Consolas, monospace; font-size: 8.8pt;
       background: #f1f5f9; padding: 0.4mm 1.2mm; border-radius: 1mm; color: #0f172a; }}
pre {{ background: #f8fafc; border: 0.5pt solid #e2e8f0; border-left: 2pt solid #0066cc;
      padding: 3mm; border-radius: 1mm; font-size: 8.6pt; overflow-wrap: break-word;
      white-space: pre-wrap; page-break-inside: avoid; margin: 0 0 4mm; }}
pre code {{ background: none; padding: 0; }}

/* ── Callouts (the manual uses > blockquotes for these) ────────────────── */
blockquote {{ margin: 0 0 4mm; padding: 3mm 4mm; background: #fffbeb;
             border-left: 2.5pt solid #f59e0b; border-radius: 0 1mm 1mm 0;
             page-break-inside: avoid; }}
blockquote p {{ margin: 0; font-size: 9.6pt; color: #78350f; }}
blockquote p + p {{ margin-top: 2mm; }}
blockquote strong {{ color: #92400e; }}

/* ── Screenshots ───────────────────────────────────────────────────────── */
/* Height cap matters as much as width: several captures are ~1440x2668, and
   at full width those overflow the text block entirely. */
img {{ display: block; max-width: 100%; max-height: 185mm; margin: 4mm auto;
      border: 0.5pt solid #e2e8f0; border-radius: 1.5mm; page-break-inside: avoid; }}
figure {{ margin: 5mm 0; page-break-inside: avoid; text-align: center; }}
figcaption {{ font-size: 8.4pt; color: #64748b; margin-top: 2mm; font-style: italic; }}
"""


def header_footer() -> tuple[str, str]:
    """Chromium header/footer templates.

    Chromium does not implement `@page` margin boxes, so the running header and
    footer are supplied here instead. `.pageNumber`/`.totalPages` are the
    class names Chromium substitutes at print time. Font size must be set
    inline — the templates do not inherit the document's stylesheet.

    Chromium applies these to every page with no per-page control, so the cover
    is rendered as a separate document without them and merged in afterwards —
    see build steps in main().
    """
    status_footer = (
        f"v{MANUAL_VERSION} &middot; August 2026"
        if STATUS.lower() == "approved"
        else f"v{MANUAL_VERSION} &mdash; {STATUS.upper()} &mdash; not for production use"
    )
    common = ("font-family:'Segoe UI',sans-serif;font-size:8pt;color:#94a3b8;"
              "width:100%;padding:0 18mm;margin:0;")
    header = (
        f'<div style="{common}display:flex;justify-content:space-between;">'
        f'<span>Oskar &mdash; User Manual</span>'
        f'<span>Scanfil APAC</span></div>'
    )
    footer = (
        f'<div style="{common}display:flex;justify-content:space-between;">'
        f'<span style="color:#cbd5e1">{status_footer}</span>'
        f'<span style="color:#64748b">Page <span class="pageNumber"></span>'
        f'</span></div>'
    )
    return header, footer


def build_html(page_map: dict[str, int], part: str = "all",
               toc_out: list | None = None) -> str:
    """part: "cover" | "body" | "all". Cover and body render as separate
    documents because Chromium applies one header/footer template to every
    page, and the cover must carry none."""
    md = markdown.Markdown(extensions=MD_EXTENSIONS)
    chapters_html: list[str] = []
    toc: list[tuple[int, str, str]] = []

    for filename, title in CHAPTERS:
        path = HERE / filename
        if not path.exists():
            print(f"  ! missing chapter, skipped: {filename}")
            continue
        md.reset()
        body = md.convert(path.read_text(encoding="utf-8"))
        cid = chapter_id(filename)
        body, entries = namespace_headings(body, cid)
        body = rewrite_links(body, cid)
        # Wrap images in <figure> so alt text becomes a printed caption — in a
        # PDF the reader cannot hover, so the alt text is otherwise lost.
        body = re.sub(
            r'<p>\s*(<img[^>]*alt="([^"]*)"[^>]*/?>)\s*</p>',
            lambda m: f"<figure>{m.group(1)}"
                      + (f"<figcaption>{m.group(2)}</figcaption>" if m.group(2) else "")
                      + "</figure>",
            body,
        )
        toc.extend(entries)
        chapters_html.append(f'<section class="chapter" id="{cid}">{body}</section>')
        print(f"  + {filename}")

    # Hand the collected TOC back so pass 1 can locate each entry in the
    # rendered PDF.
    if toc_out is not None:
        toc_out.extend(toc)

    # data-page is filled in on the second pass — see the two-pass note in the
    # module docstring. On pass 1 it is empty, and the CSS
    # `content: attr(data-page)` simply renders nothing.
    toc_items = "\n".join(
        f'<li class="lvl{lvl}"><a href="#{anchor}" '
        f'data-page="{page_map.get(anchor, "")}">{html.escape(text)}</a></li>'
        for lvl, anchor, text in toc
    )

    revisions = "\n".join(
        f"<tr><td><strong>{v}</strong></td><td>{d}</td><td>{html.escape(n)}</td></tr>"
        for v, d, n in REVISIONS
    )

    built = date.today().strftime("%d %B %Y")
    sha, tree = git_describe()
    source = f"{sha} ({tree})" if sha else "not recorded"
    approved = "approved" if STATUS.lower() == "approved" else ""

    status_footer = (
        f"v{MANUAL_VERSION} · August 2026"
        if STATUS.lower() == "approved"
        else f"v{MANUAL_VERSION} — {STATUS.upper()} — not for production use"
    )

    draft_note = "" if STATUS.lower() == "approved" else f"""
  <div class="status-note"><p><strong>This is a {STATUS.lower()}.</strong> It has not been
  formally approved, and has not yet been trialled with users. Treat the content as accurate but
  provisional, and send corrections to the {OWNER} before it is issued.</p></div>"""

    cover_open = "" if part in ("cover", "all") else "<!--"
    cover_close = "" if part in ("cover", "all") else "-->"
    body_open = "" if part in ("body", "all") else "<!--"
    body_close = "" if part in ("body", "all") else "-->"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Oskar — User Manual v{MANUAL_VERSION} ({STATUS})</title>
<style>{css(status_footer, part)}</style></head><body>
<div class="__probe__" style="position:absolute;top:0;left:0;width:1px;height:265mm;visibility:hidden"></div>

{cover_open}<div class="cover"><div class="cover-inner">
  <div class="mark">O</div>
  <h1>Oskar</h1>
  <p class="sub">User Manual — Engineering Change Notes</p>
  <div class="badge {approved}">{STATUS}</div>
  <div class="meta">
    <strong>Version {MANUAL_VERSION}</strong> &nbsp;·&nbsp; {built}<br>
    <strong>Scanfil APAC</strong><br>
    Replaces Stargile for ECN management
  </div>
</div>
<div class="docref">
  Describes Oskar as at August 2026 &nbsp;·&nbsp; Source revision {source}
  &nbsp;·&nbsp; Owner: {OWNER}
</div></div>{cover_close}

{body_open}<div class="frontmatter">
  <h1>About this manual</h1>
{draft_note}
  <table class="doc-control">
    <tbody>
      <tr><td>Version</td><td><strong>{MANUAL_VERSION}</strong></td></tr>
      <tr><td>Status</td><td><strong>{STATUS}</strong></td></tr>
      <tr><td>Issued</td><td>{built}</td></tr>
      <tr><td>Owner</td><td>{OWNER}</td></tr>
      <tr><td>Applies to</td><td>Oskar as at August 2026</td></tr>
      <tr><td>Source revision</td><td><code>{source}</code></td></tr>
    </tbody>
  </table>

  <h2>Revision history</h2>
  <table>
    <thead><tr><th>Version</th><th>Date</th><th>Change</th></tr></thead>
    <tbody>{revisions}</tbody>
  </table>

  <h2>What Oskar does</h2>
  <p>Oskar is the system Scanfil APAC uses to raise, review and approve <strong>Engineering
  Change Notices</strong> (ECNs), and to push approved changes into Movex. It replaces
  <strong>Stargile</strong>.</p>
  <p>Movex remains the single source of truth for items, BOMs and routings. Oskar governs how
  changes get into it.</p>

  <h2>You do not need to read all of this</h2>
  <table>
    <thead><tr><th>If you…</th><th>Read</th><th>Roughly</th></tr></thead>
    <tbody>
      <tr><td><strong>Raise changes</strong><br>engineer, designer, originator</td>
          <td>1, 2, <strong>3</strong>, 7, 9, 10 — plus 6 if you work with BOMs</td>
          <td>Two hours, plus hands-on</td></tr>
      <tr><td><strong>Approve changes</strong><br>EM, QM, PM, Supply Chain, Finance</td>
          <td>1, 2, <strong>4</strong>, 8, 10</td>
          <td>Thirty minutes</td></tr>
      <tr><td><strong>Are a Document Controller</strong></td>
          <td>Everything, in order — the DC is the only role that touches every part</td>
          <td>Half a day</td></tr>
      <tr><td><strong>Are a Senior or Chief Engineer</strong></td>
          <td>1, 2, 4 (Engineering Review section), 6</td><td>An hour</td></tr>
      <tr><td><strong>Came from Stargile</strong></td>
          <td>Start at 11 — what moved, what's gone, which habits to unlearn</td>
          <td>Twenty minutes</td></tr>
      <tr><td><strong>Cannot sign in</strong></td><td>12</td><td>Five minutes</td></tr>
    </tbody>
  </table>

  <h2>Getting help</h2>
  <table>
    <thead><tr><th>Problem</th><th>Who</th></tr></thead>
    <tbody>
      <tr><td>Can't sign in, or no buttons appear where you expect them</td><td>IT</td></tr>
      <tr><td>An ECN is stuck, or a Movex write failed</td><td>Your Document Controller</td></tr>
      <tr><td>Not sure whether something needs an ECN at all</td><td>Your Engineering Manager</td></tr>
      <tr><td>Something in this manual is wrong or unclear</td>
          <td>The {OWNER} — please say so, it will be fixed</td></tr>
    </tbody>
  </table>

  <blockquote><p><strong>Screens change.</strong> If what you see differs from what is written
  here, trust the screen and report the difference.</p></blockquote>

  <h2>Example spreadsheets</h2>
  <p>Ready-to-use templates for all four bulk uploads ship alongside this manual in the
  <code>templates/</code> folder: item, routing, BOM change and MPN.</p>
</div>

<div class="chapter toc" id="contents">
  <h1>Contents</h1>
  <ol>{toc_items}</ol>
</div>

{"".join(chapters_html)}{body_close}
</body></html>"""


RENDER_JS = r"""
const { chromium } = require('playwright');

(async () => {
  const [htmlPath, pdfPath, headerHtml, footerHtml, marginCss, showFurniture] =
    process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file:///' + htmlPath.split('\\').join('/'), { waitUntil: 'load' });
  await page.emulateMedia({ media: 'print' });

  const opts = {
    path: pdfPath,
    format: 'A4',
    printBackground: true,
    // Playwright's margin option overrides the stylesheet's @page margin, so
    // it must be supplied per document — the cover needs zero for its
    // full-bleed background, the body needs room for the running furniture.
    displayHeaderFooter: showFurniture === 'yes',
    headerTemplate: headerHtml,
    footerTemplate: footerHtml,
    margin: JSON.parse(marginCss),
  };
  await page.pdf(opts);

  // Pass 1 needs no probe: page numbers are recovered from the rendered PDF
  // itself in Python (see locate_headings). An earlier version estimated them
  // as elementOffset / pageHeight, which was wrong by several pages — that
  // arithmetic assumes content flows continuously and ignores the gaps left by
  // `page-break-before` on every chapter.

  await browser.close();
})();
"""


def _render(html_path: Path, pdf_path: Path, header: str, footer: str,
            margin: dict[str, str] | None = None,
            furniture: bool = True) -> None:
    # Written into frontend/, not next to this script: Node resolves
    # `require('playwright')` from the script's own directory upwards, and
    # only frontend/ has node_modules.
    js = FRONTEND / "_render-manual.cjs"
    js.write_text(RENDER_JS, encoding="utf-8")
    env = {**os.environ,
           "PLAYWRIGHT_BROWSERS_PATH": os.environ.get(
               "PLAYWRIGHT_BROWSERS_PATH",
               str(Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"))}
    try:
        proc = subprocess.run(
            ["node", str(js), str(html_path), str(pdf_path), header, footer,
             json.dumps(margin or {"top": "20mm", "bottom": "18mm",
                                   "left": "18mm", "right": "18mm"}),
             "yes" if furniture else "no"],
            cwd=FRONTEND, capture_output=True, text=True, env=env, timeout=600,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "Chromium render failed:\n" + proc.stdout + "\n" + proc.stderr
            )
    finally:
        js.unlink(missing_ok=True)


def locate_headings(pdf_path: Path, toc: list[tuple[int, str, str]],
                    page_offset: int) -> dict[str, int]:
    """Find the printed page of each contents entry by reading the rendered PDF.

    Chromium has no `target-counter()`, and estimating from element offsets is
    wrong once `page-break-before` starts leaving gaps — an earlier version did
    that and was off by several pages. Reading the finished text is exact.

    Headings are matched in document order and the search only ever moves
    forward, so repeated headings (several chapters have a "What happens next")
    resolve to the right occurrence rather than always the first.

    `page_offset` accounts for the cover, which is merged in front of this
    document and so shifts every page number by one.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = [(pg.extract_text() or "").replace("\n", " ") for pg in reader.pages]
    norm = [re.sub(r"\s+", " ", t).lower() for t in pages]

    # Skip the contents pages themselves. They list every heading in the book,
    # so searching from page 1 matches each entry against its own TOC line and
    # reports the contents page for everything. The first page after the last
    # contents page is where real content starts.
    first_content = 0
    for i, t in enumerate(norm):
        if "contents" in t[:400] and any(h[2].lower() in t for h in toc[:3]):
            first_content = i + 1
    # Walk past any further contents overflow pages.
    while first_content < len(norm) and norm[first_content].count("…") > 5:
        first_content += 1

    found: dict[str, int] = {}
    cursor = first_content
    for _lvl, anchor, text in toc:
        needle = re.sub(r"\s+", " ", text).strip().lower()
        if not needle:
            continue
        for i in range(cursor, len(norm)):
            if needle in norm[i]:
                found[anchor] = i + 1 + page_offset
                cursor = i          # never search backwards
                break
    return found


def main() -> int:
    if not (FRONTEND / "node_modules" / "playwright").exists():
        print(f"ERROR: playwright not installed in {FRONTEND}.")
        print("       Run: cd frontend && npm install --save-dev playwright")
        return 1

    print(f"Oskar User Manual v{MANUAL_VERSION} ({STATUS})")
    header, footer = header_footer()
    cover_pdf = HERE / "_cover.pdf"
    body_pdf = HERE / "_body.pdf"

    try:
        # Pass 1 — lay the body out, then read back which page each heading
        # actually landed on. +1 because the cover is merged in front.
        print("Pass 1: layout…")
        toc: list[tuple[int, str, str]] = []
        OUT_HTML.write_text(build_html({}, part="body", toc_out=toc), encoding="utf-8")
        _render(OUT_HTML, body_pdf, header, footer)
        page_map = locate_headings(body_pdf, toc, page_offset=0)
        print(f"        located {len(page_map)}/{len(toc)} headings")

        # Pass 2 — same body, now with real page numbers in the contents.
        # Adding them can only reflow the contents pages themselves, and those
        # sit before all the located content, so the numbers stay valid.
        print("Pass 2: contents page numbers…")
        OUT_HTML.write_text(build_html(page_map, part="body"), encoding="utf-8")
        _render(OUT_HTML, body_pdf, header, footer)

        # Cover: no header/footer template, so it renders as its own document.
        print("Cover…")
        cover_html = HERE / "_cover.html"
        cover_html.write_text(build_html({}, part="cover"), encoding="utf-8")
        _render(cover_html, cover_pdf, "", "",
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                furniture=False)
        cover_html.unlink(missing_ok=True)

        print("Merging…")
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.append(str(cover_pdf))
        writer.append(str(body_pdf))
        writer.add_metadata({
            "/Title": f"Oskar User Manual v{MANUAL_VERSION} ({STATUS})",
            "/Author": "Scanfil APAC",
            "/Subject": "Engineering Change Notices — user manual",
            "/Keywords": f"Oskar, ECN, Movex, Scanfil APAC, v{MANUAL_VERSION}, {STATUS}",
        })
        with open(OUT_PDF, "wb") as fh:
            writer.write(fh)
        writer.close()
    finally:
        for tmp in (cover_pdf, body_pdf):
            tmp.unlink(missing_ok=True)

    from pypdf import PdfReader
    pages = len(PdfReader(str(OUT_PDF)).pages)
    size_kb = OUT_PDF.stat().st_size / 1024
    print(f"\n  {OUT_PDF.name}  —  {pages} pages, {size_kb:,.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
