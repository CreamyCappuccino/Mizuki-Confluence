#!/usr/bin/env python3
"""Validate the Confluence proposal/fixture offline. Never publishes or uses a DB."""
import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from contract_html_policy import ContractError, validate_fixture_html, validate_https_url

VERSION = "confluence.publication.v1"
FIELDS = frozenset(
    "schema_version destination_key manuscript_ref revision_ref revision_no "
    "edition_ref locale destination_ref destination_url title excerpt rendered_html "
    "renderer_version author_label authors category_paths tags published_on "
    "content_updated_at visibility".split()
)
AUTHOR_FIELDS = frozenset(
    "author_ref persona_name harness model role provenance_source".split()
)
FIXTURE_FIELDS = frozenset(
    "fixture_only site_base_url payload_snapshot expected_payload_sha256".split()
)
MAX_BYTES = 2_000_000


def _object(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise ContractError(f"{label}: fields must match the versioned contract")


def _text(value, label, *, nullable=False, limit=10000):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ContractError(f"{label}: invalid text")


def _timestamp(value, label):
    if value is None:
        return
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value
    ):
        raise ContractError(f"{label}: offset ISO8601 timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError
    except ValueError as exc:
        raise ContractError(f"{label}: invalid timestamp") from exc


def payload_sha256(payload):
    """Same JSON encoding choices as Pressroom's _normalize_payload."""
    try:
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("payload is not canonical-JSON serializable") from exc
    return hashlib.sha256(raw).hexdigest()


def validate_payload(payload, *, site_base_url):
    """Validate the candidate shape. Passing this is NOT publication authority."""
    _object(payload, FIELDS, "payload_snapshot")
    if payload["schema_version"] != VERSION or payload["destination_key"] != "confluence":
        raise ContractError("schema_version/destination_key mismatch")
    ref = payload["manuscript_ref"]
    if not isinstance(ref, str) or not re.fullmatch(r"ART[0-9]{4,}", ref):
        raise ContractError("manuscript_ref: ART reference required")
    number = payload["revision_no"]
    if type(number) is not int or number < 1:
        raise ContractError("revision_no: positive integer required")
    if payload["revision_ref"] != f"{ref}-R{number:02d}":
        raise ContractError("revision_ref does not match manuscript/revision_no")
    edition = payload["edition_ref"]
    if edition is not None and (
        not isinstance(edition, str) or not re.fullmatch(r"EDN[0-9]{4,}", edition)
    ):
        raise ContractError("edition_ref: EDN reference or null required")
    if payload["locale"] not in ("ja", "en"):
        raise ContractError("locale: ja/en required")
    if payload["visibility"] != "unlisted":
        raise ContractError("Phase 1 exposes only explicitly selected unlisted writing")
    if payload["destination_ref"] != f"confluence:{ref}":
        raise ContractError("destination_ref: wrong stable identity")
    validate_https_url(site_base_url)
    base = urlsplit(site_base_url)
    if base.query or base.fragment or "%" in base.path or ".." in base.path:
        raise ContractError("site_base_url: use a normalized configured base")
    expected_url = f'{site_base_url.rstrip("/")}/{payload["locale"]}/articles/{ref.lower()}.html'
    if payload["destination_url"] != expected_url:
        raise ContractError("destination_url does not match the configured route")

    _text(payload["title"], "title", limit=1000)
    _text(payload["renderer_version"], "renderer_version", limit=200)
    _text(payload["rendered_html"], "rendered_html", limit=1_500_000)
    for field in ("excerpt", "author_label"):
        value = payload[field]
        if value != "":
            _text(value, field, nullable=True, limit=4000)
    validate_fixture_html(payload["rendered_html"])

    if not isinstance(payload["authors"], list):
        raise ContractError("authors: array required")
    for author in payload["authors"]:
        _object(author, AUTHOR_FIELDS, "authors[]")
        if not isinstance(author["author_ref"], str) or not re.fullmatch(
            r"AUT[0-9]{4,}", author["author_ref"]
        ):
            raise ContractError("authors[].author_ref: AUT reference required")
        _text(author["persona_name"], "authors[].persona_name", limit=200)
        for field in ("harness", "model"):
            _text(author[field], f"authors[].{field}", nullable=True, limit=200)
        if author["role"] not in ("primary", "translator", "editor"):
            raise ContractError("authors[].role: unsupported")
        if author["provenance_source"] not in ("supplied", "backfilled", "inferred"):
            raise ContractError("authors[].provenance_source: unsupported")
    paths, tags = payload["category_paths"], payload["tags"]
    if not isinstance(paths, list) or not isinstance(tags, list):
        raise ContractError("taxonomy: arrays required")
    for path in paths:
        if not isinstance(path, list) or not path:
            raise ContractError("category_paths[]: nonempty hierarchy required")
        for part in path:
            _text(part, "category_paths[][]", limit=200)
    for tag in tags:
        _text(tag, "tags[]", limit=200)
    try:
        day = payload["published_on"]
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
            raise ValueError
    except ValueError as exc:
        raise ContractError("published_on: YYYY-MM-DD required") from exc
    _timestamp(payload["content_updated_at"], "content_updated_at")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ContractError("JSON contains a non-finite value")


def load_fixture(path):
    with Path(path).open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ContractError("fixture exceeds the offline size bound")
    try:
        doc = json.loads(raw, object_pairs_hook=_unique_object,
                         parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("fixture is not UTF-8 JSON") from exc
    _object(doc, FIXTURE_FIELDS, "fixture envelope")
    if doc["fixture_only"] is not True:
        raise ContractError("offline CLI accepts synthetic fixtures only")
    _text(doc["site_base_url"], "site_base_url", limit=2000)
    if urlsplit(doc["site_base_url"]).hostname != "confluence.invalid":
        raise ContractError("fixture destination must be confluence.invalid")
    validate_payload(doc["payload_snapshot"], site_base_url=doc["site_base_url"])
    digest = payload_sha256(doc["payload_snapshot"])
    if digest != doc["expected_payload_sha256"]:
        raise ContractError("fixture payload hash mismatch")
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    try:
        fixture = load_fixture(args.fixture)
    except (OSError, TypeError, ValueError) as exc:
        # Never echo payloads or private paths in diagnostic output.
        reason = str(exc) if isinstance(exc, ContractError) else "unable to read fixture"
        print(f"contract: rejected | {reason}")
        return 1
    payload = fixture["payload_snapshot"]
    print(f'contract: valid | {payload["manuscript_ref"]} / {payload["revision_ref"]}')
    print(f'sha256: {fixture["expected_payload_sha256"]}')
    print("mode: fixture-only | DB/network/publication: not used")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
