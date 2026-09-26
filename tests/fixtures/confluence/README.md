# Synthetic one-article contract fixture

`publication_v1.json` holds a **proposed prepared payload**, wrapped in offline
testing metadata. It is not a live manuscript, PUB/APR/JOB, or publication receipt.

- All article text, author identity, IDs, and timestamps are synthetic.
- Fake ART/AUT identifiers are not reserved; never look them up in a live DB.
- `confluence.invalid` is a non-deployment example origin. No network is used.
- The expected hash is over `payload_snapshot` only, not this fixture envelope.\n- `site_policy` is fixture/testing metadata for the destination-level discovery policy; it is deliberately separate from article `visibility`.
- A rehearsal must create its own synthetic manuscript through Pressroom and
  use the actual returned identifiers and explicit approval.
- Do not replace this committed fixture with private content or a production dump.

The optional `edition_ref`, `excerpt`, author label and content update timestamp
are explicitly nullable in the contract; category paths and tags can be empty.
Unit tests exercise these cases without adding more pretend published articles.

See [the contract proposal](../../../docs/CONFLUENCE_PRESSROOM_CONTRACT_V1.md).
