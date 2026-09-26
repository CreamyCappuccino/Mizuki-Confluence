# v0.2 verification — 2026-09-26

## Source boundary

Based on the repository at `92deb05dab92ac40c849f87131343ffffb7ec0f1`
and the newer conversation corrections captured in `CONFLUENCE_VISUAL_V02.md`.
No real Pressroom data, existing private AIL manuscripts, credentials, or
external stock-photo bytes were imported.

## Checks performed

- Python source compilation and regeneration of all five static HTML pages.
- JavaScript syntax checks with Node.js 22.16.0.
- Chromium 144.0.7559.96 rendering through Playwright.
- Twelve viewport/theme combinations: widths 320, 390, 820, 1024, 1440, and
  1920 CSS pixels, each in system-light and system-dark.
- No horizontal page overflow; first article begins inside the initial
  viewport in every case. Examples: 544px at 390×844; 557px at 820×960;
  586px at 1440×960.
- Japanese/English interface switching, with Japanese article regions still
  identified as Japanese. English labels did not introduce overflow.
- Six initial sample entries expand to ten in place; the exhausted button
  disappears. It does not fold already-read entries away.
- Search for `Claude` returned three fixtures; unmatched text showed an empty
  state; clearing restored the expanded list.
- Two-scene switch, explicit day/night theme controls, menu open/Escape close.
- Reduced-motion disables the flow animation; text stays visible.
- An artificially long title did not cause horizontal page overflow.
- JavaScript disabled: all ten writing fixtures remained readable.
- Mobile rendering of writers, browse, replies, and reading pages.
- Reading-page reply fragment selects the matching sample and reply region.
- 131 local links/fragment targets checked for existence; no duplicate IDs.
- No network requests or uncaught JavaScript errors during the tested renders.
- Visual inspection of desktop, half-width, mobile, and night screenshots.

## Limitations — not claimed as tested

This runtime's browser policy blocked both `file://` navigation and localhost
HTTP navigation. The browser checks therefore loaded the **same authored local
HTML, CSS, JS, and image bytes in memory**. The harness only inlines asset
references and removes the favicon link; it does not redesign the page.

Consequently, actual navigation between files, browser-back restoration,
storage persistence across real page loads, and Mac/Safari font/rendering
behavior still require the owner's local check. Local link targets were
validated statically, not by claiming a successful navigation crawl.

The remaining publication workflow, production pagination, data-driven reply
refresh, search indexing, true language editions, and deployment are not part
of this prototype. The medium-resolution photo crops are provisional.

## Re-run

`python tools/build_prototype.py`

`python tests/prototype_smoke.py --browser /path/to/chromium --screenshots /tmp/confluence-review`

The optional browser test needs an existing Playwright Python installation and
Chromium. Opening `prototype/index.html` itself requires no dependencies.
