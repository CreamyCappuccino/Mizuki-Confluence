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

## Pressroom connection — contract review gate

[Phase 1 contract proposal](docs/CONFLUENCE_PRESSROOM_CONTRACT_V1.md) and
[one synthetic article fixture](tests/fixtures/confluence/README.md) are ready
for integration review. The offline validator and 18 unit tests check payload
shape, identity, dates, taxonomy, public-field boundaries, and deterministic hashes.
This is not a registered destination or a completed PUB/APR/JOB publishing path.
The v0.2 visual prototype remains unchanged.

```sh
python3 tools/validate_confluence_contract.py tests/fixtures/confluence/publication_v1.json
python3 -m unittest discover -s tests -p 'test_confluence_contract.py' -v
```

## Repository principle

**Public code, private content.**

Local/private manuscripts should stay outside the public repository or in explicitly ignored local paths. Content intended for publication should enter Confluence through the publishing workflow rather than by committing private source material directly.
