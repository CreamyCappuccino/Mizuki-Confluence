# Mizuki-Confluence

Confluence is a shared writing space where different streams—people, AIs, memories, knowledge, research, drafts, and creative work—can meet without being flattened into one form.

This repository is the public codebase for Confluence. Private manuscripts and sensitive content do **not** belong in this repository.

## Project status

The visual prototype is at **v0.2**. Open `prototype/index.html` in a browser;
keep `prototype/assets/` alongside it. No build or installation is required.

It includes day/night/system themes, local scene images, a Japanese/English
interface, in-place writing expansion, sample search, and local writer/browse/
reply/reading pages. All entries and reply events are **synthetic layout data**.

- [Prototype instructions](prototype/README.md)
- [Current design delta](docs/CONFLUENCE_VISUAL_V02.md)
- [Verification and limitations](docs/CONFLUENCE_V02_VERIFICATION.md)
- [Original top-page design baseline](docs/CONFLUENCE_TOP_PAGE_DESIGN_V1.md)

The real publishing flow, author model, Pressroom integration, and production
frontend/data architecture remain separate work. The optional Python stdlib
prototype builder does not prescribe the backend stack.

## Repository principle

**Public code, private content.**

Local/private manuscripts should stay outside the public repository or in explicitly ignored local paths. Content intended for publication should enter Confluence through the publishing workflow rather than by committing private source material directly.
