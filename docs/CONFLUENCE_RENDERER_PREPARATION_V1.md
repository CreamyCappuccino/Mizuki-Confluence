# Renderer handoff → pre-PUB preparation

Date: 2026-09-27 (+08). Branch: `integration/provider-rehearsal-v1`.
Status: captured-renderer preparation and read-only provider-half implemented;
**not a registered adapter or completed PUB/APR/JOB rehearsal**.

## Sources and scope

- Confluence base: `6df24639acada21a0725cc72c16f9b8c1202544d`.
- Codex renderer handoff: `56b3c3a7fcc0d606035acfa7eb454079a8168832`,
  `tests/fixtures/confluence/renderer/` (five original files retained unchanged).
- Maintainer's formal supplement: CX-MSG0233, carrying the RLY2863 supplement.
- Contract: `CONFLUENCE_PRESSROOM_CONTRACT_V1.md`; visual baseline v0.2 unchanged.

The raw fixture is actual renderer output from a synthetic Markdown document,
not a real manuscript. Its author ran the actual byte replay in the recorded
Pressroom environment. This change consumes those captured bytes; it does not
pretend to rerun that unavailable dependency chain in the ChatGPT container.

Raw output has no heading IDs, percent-encoded Japanese fragment links with
no targets yet, and `rel="noopener noreferrer"` added by the renderer.
The previous preparation implementation could not resolve those fragments and
rejected `rel`. It must not be bypassed by editing the raw evidence or accepting
unprepared input as already-approved HTML.

## Implemented normalization, before PUB only

`src/confluence/html_prepare.py`, `html_fragments.py`, `html_policy.py`:

1. Reject unsupported elements, duplicate/bare attributes, comments, document
   declarations, malformed/unbalanced input, control characters and size/depth
   limits. A syntax-only guard does not sanitize or emit output.
2. Parse with pinned lxml/libxml2; rebuild only fixed allowlisted tags and
   attributes with escaped text. Network resolution is disabled.
3. Assign `cf-n-NNNN` IDs by document element order. Explicit original IDs take
   priority over heading-label aliases. Heading labels use NFC and collapsed
   whitespace. With repeated heading labels, label links target the first
   occurrence; the headings themselves keep distinct generated IDs.
4. Decode local fragments once as strict UTF-8. Missing/ambiguous-unrecognized
   spellings fail; there is no fuzzy matching or invented `-2` suffix convention.
5. Strip only renderer `rel` tokens from the known set `noopener noreferrer`.
   `target` remains forbidden; links are same-tab. Unknown attributes/relations,
   dangerous or unresolved URLs, and embedded images remain rejected.
6. Recheck canonical prepared bytes. Validation after PUB does not normalize
   or repair anything. Any content change also needs the existing payload-hash
   and exact-revision checks at dispatch, which this preparation half cannot
   substitute for.

Policy version: `confluence-prose-v2+lxml-6.1.1`, libxml2 `2.14.6`.
Parser version and policy participate in configuration identity. A different
parser build requires a deliberate compatibility review, not silent fallback.
These checks remain private-rehearsal code, not a claim of complete production
XSS/security review. The existing `tools/contract_html_policy.py` stays an
independent offline fixture checker; it was not turned into the sanitizer.

For this fixture both Japanese links target `#cf-n-0006`. The repeated heading
has `cf-n-0034`. IDs are stable for the same prepared revision; cross-revision
fragment stability is not promised. Article routes still use ART identity.

## Payload and preparation provider

`preparation.py` still consumes the exact selected revision's saved
`rendered_html` and `renderer_version`. It does not rerender Markdown at dispatch.
The original renderer identity and new preparation-policy version are both kept.
The prior-publication fallback now checks the manuscript identity before reusing
its date; a different ART or locale cannot supply the date/route implicitly.

`provider.py:create_preparation_provider` is the **read-only preparation half**.
After verifying explicit local dependency roots, it uses actual Pressroom
`PreparedPublication` / `PublicationPreview` types. It provides no publish,
unpublish, registry or worker methods and must not be registered as a complete
`RecoverableDestinationAdapter`. Its source resolver is an injected canonical
read port; the concrete repository/authority composition is still outstanding.
Unit DTO doubles below test this boundary, not a real Pressroom transaction.

The immutable candidate remains separate from publication success. No premature
`published` state, actual ledger timestamps, private actor/session data, or
whole original manuscript is exported. No new editable manuscript database exists.

## Dependency gate — local source identity is not a remote installation pin

`dependency_pin.py` and `tools/check_rehearsal_dependencies.py` check explicit
checkout roots, clean HEAD and package trees, lock/source hashes, imported module
locations, Python and resolved dependency versions. No clone, fetch, sync,
installation, `.env` lookup or older-version fallback is performed.

Recorded actual dependency identities:
- Pressroom: `b5ce8d9422f0b90377145471bcb96f870e3e9263`.
- Converter: `0d98198dd2da1abf82e4cf17c1bf8658027f021c`.
- Exact versions and file hashes: original renderer `provenance.json`.

The maintainer reports the Pressroom commit is not reachable via GitHub and the
converter checkout has no origin. This change **does not fix distribution by
publishing either private source or falling back to an older remote commit**.
A verified existing local environment can be used for the next isolated test.
This environment has not passed that live dependency gate. Missing checkouts
fail before the provider source port is read.

## Reproduce the completed checks

```sh
python3 tests/fixtures/confluence/renderer/verify_fixture.py
python3 tools/prepare_renderer_fixture.py
python3 -m unittest discover -s tests -p 'test_*prepar*.py' -v
python3 tests/preparation_browser_smoke.py --browser /path/to/chromium
```

Observed here: 38 new unit tests passed; compile checks passed. Chromium
in-memory checks passed at 390/1440 px: unique heading targets, preserved code
characters/table, no active elements, no horizontal overflow or network requests.
This browser check is a fragment-only diagnostic, **not** the production UI,
HTTP route/readback, navigation history, or full sanitizer acceptance test.

`prepared_renderer_v1.json` is a new synthetic candidate fixture, not a receipt:
- raw HTML SHA-256: `e72825edcb09a86c001c8861f755901b64886c28da9e353912582a7254ea87d7`
- prepared HTML SHA-256: `094edc2045e8882e840c6d66b8621f371393cc793942b9a4a0f0b3c893aa1c0a`
- prepared payload SHA-256: `25a68ca36ee8bc507c02e78f08ef9e5da118d2ce5a4e4e756cb9d08d546f6dc6`

The original 19 contract tests were reported PASS by the maintainer; this change's
38-test count does not silently include or claim a local rerun of that suite.

## Remaining work and ownership

Confluence: complete recoverable adapter, canonical authority/locking wiring,
projection storage, static build and actual route/body readback. The v0.2 sample
UI and `main` stay unchanged during this integration work.

Joint next check: run the dependency gate and actual renderer replay followed
by this preparation path in the maintainer's verified local environment. Use a
separate private rehearsal DB/output only after its composition is fixed.
Create a synthetic ART via real returned refs, then test PUB→APR→JOB,
same-key retry, external-success/ledger-failure recovery, revision, stale work,
and withdrawal. No production registration, original manuscripts or live
publication operations are authorized by a passing fixture test.
