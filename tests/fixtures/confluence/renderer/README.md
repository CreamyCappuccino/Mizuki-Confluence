# Real Pressroom renderer fixture

Created 2026-09-27 for CX-MSG0225 / TSK1925. All prose is synthetic and public-safe.
This directory is deliberately self-contained; no main/provider files are changed.

- `input.md`: Japanese headings, repeated heading text, two links to the same
  heading, fenced code, inline code, table, quote, list and an example HTTPS link.
- `output.html`: exact UTF-8 output of `MarkdownRenderer().render(input_text).html`.
- `provenance.json`: source commits/tree hashes, resolved dependency versions,
  renderer version and byte SHA-256s. No private paths or source manuscripts.
- `verify_fixture.py`: read-only integrity check; optional actual-renderer replay.

## Dependency identity

Pressroom checkout: `b5ce8d9422f0b90377145471bcb96f870e3e9263` in
`CreamyCappuccino/CodexMizuki-Pressroom`. Its `pyproject.toml` uses a local editable
`md-converter` source, not a Git commit pin. The converter checkout used here is
`0d98198dd2da1abf82e4cf17c1bf8658027f021c`, package
`packages/md-converter`, with **no origin remote configured**. Both source trees
were clean. These are local source identities, not deployed-runtime proof or a
promise that either commit is fetchable remotely.

Resolved versions: md-converter 0.1.0, markdown-it-py 4.2.0, nh3 0.3.6,
PyYAML 6.0.3. The run used the existing Pressroom environment without sync/install
or lock changes; Python 3.14.7. `uv --no-sync` warned that the interpreter differed
from the environment creation version (3.14.4). Replay below passed despite that
warning. Pin source identities **and** dependency versions for the rehearsal.

## Replay

From the Confluence checkout, Python stdlib integrity check:

```sh
python3 tests/fixtures/confluence/renderer/verify_fixture.py
```

From a clean Pressroom checkout with the pinned converter installed, pass the
absolute path of this directory's verifier (substitute your actual checkout):

```sh
uv run --frozen --no-sync python /absolute/confluence/tests/fixtures/confluence/renderer/verify_fixture.py --rerender
```

No command reads a manuscript DB, creates ART/PUB/APR/JOB, publishes or contacts
the example HTTPS origin. The verifier does not install dependencies or assert
full checkout/runtime equivalence; the recorded tree/lock identities are evidence
for the later composition pin review.

## Provider preparation boundary

This is **raw renderer output**, not `publication_v1.json` or an approved payload.
Current Pressroom rendering emits no heading IDs. Japanese fragments are
percent-encoded and do not yet have targets. Links also carry renderer-added
`rel="noopener noreferrer"`, outside the current Confluence fixture allowlist.
Consequently raw output is expected to fail `validate_fixture_html`.

The Confluence provider must define a deterministic pre-PUB heading/fragment
mapping (including repeated heading text), normalize allowed attributes, and
validate/sanitize under its versioned policy. Both repeated links must resolve
to the same explicitly chosen heading; duplicate headings need unique IDs.
Only then may it freeze/hash the prepared payload. Never patch this raw fixture
to pretend the renderer already emits `cf-*` IDs, or repair dispatch after PUB.

The byte replay proves the renderer seam only. Provider preparation, browser
behavior, real PUB/APR/JOB, retry/recovery and delivery readback remain separate
gates for the Confluence implementation/rehearsal.
