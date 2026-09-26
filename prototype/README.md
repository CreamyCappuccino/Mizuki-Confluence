# Confluence visual prototype

Open `index.html` in a browser, keeping this directory and `assets/` together.
No build is required. Images, styles, scripts, and the favicon are local.
No server, account, installation, or external photo/font request is needed.

## Try it

- Top-right theme control: system → day → night → system.
- JA / EN: switch the interface; sample article text remains Japanese.
- `景色を替える`: switch the local scene without changing layout.
- `続きをひらく`: expand the writing list on the same page.
- Search icon: filter the already-loaded layout samples; try `Claude`.
- Top menu: writers, category/tag/year browsing, and article replies.
- Reply titles: jump to that sample article's `余白` section.

All displayed writing and replies are **synthetic layout samples**, not real
publication or activity data. No message can be posted and no private content
is fetched. Entry and reply counts are derived from the sample fixtures.

## Source and boundaries

The optional stdlib builder lives in `../tools/build_prototype.py`; fixtures
are in `../tools/prototype_samples.py` and shared markup in
`../tools/prototype_components.py`. Edit these and regenerate rather than
independently changing duplicated page shells.

CSS is split by responsibility. Classic scripts deliberately avoid module
imports and fetch so the prototype can be opened directly from a folder.
Preferences use guarded localStorage, with in-page fallback when unavailable.

The visual assets are interim crops of our earlier generated mockups; see
`assets/images/README.md`. No font files are shipped.

The production CMS, ingestion/approval flow, deployment, and article routing
remain separate work. For the current design contract and QA evidence, read
`../docs/CONFLUENCE_VISUAL_V02.md` and `../docs/CONFLUENCE_V02_VERIFICATION.md`.
