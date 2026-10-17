# Renderer-owned HTML metadata design — 2026-10-18

Owner: Mizuki / ChatGPT
Scope: documentation only; no source, runtime, Pressroom JOB, or published-site mutation.

## Changed
- Added `docs/CONFLUENCE_HTML_METADATA_V3.md`, informed by Shared MN26 design principles (and MN19 code principles).
- Chose renderer-authored basic OG tags plus canonical link and normal raw-exact public readback for **new** frozen artifacts.
- Separated legacy `JOB0154`/`here-now-og/v2` evidence from future default behavior.
- Identified the minimal renderer, runtime selection and focused-test work; kept Stage B withdrawal a separate later action.

## Why
An independent Here.now probe showed that author-authored OG HTML stayed byte-exact in its limited test while pages without OG tags were rewritten after publication. New per-JOB transform policies would make ordinary future publishing harder without solving a new product need.

## Source and next
Design: `docs/CONFLUENCE_HTML_METADATA_V3.md`.
Baseline code before design: `be6c7043f489d9c1f21c4e6dc469bde55604e029`.
Next: implement the renderer metadata and new-JOB exact path in Confluence; test before a separately authorized live release. Do not rewrite the frozen JOB0154 artifact or use HNR direct writes as a Pressroom release substitute.
