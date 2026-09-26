"""Validate immutable dispatch identity/hash before any destination side effect.

The Pressroom ledger is the approval authority. These guards compare its exact
frozen payload; they never rebuild, sanitize, or repair an approved candidate.
"""
from __future__ import annotations

from copy import deepcopy
import hmac
import re
from uuid import UUID

from .payload import ART, _route, payload_sha256

UNPUBLISH_FIELDS = frozenset({
    "operation_kind", "destination_ref", "destination_url", "published_revision_id",
})


def checked_payload(dispatch, *, action: str | None = None) -> dict[str, object]:
    if dispatch.action not in {"publish", "unpublish"}:
        raise ValueError("unsupported publication action")
    if action is not None and dispatch.action != action:
        raise ValueError("publication action mismatch")
    if dispatch.destination_key != "confluence":
        raise ValueError("publication destination mismatch")
    if not isinstance(dispatch.idempotency_key, str) or not dispatch.idempotency_key.strip():
        raise ValueError("publication idempotency key required")
    if not isinstance(dispatch.payload_snapshot, dict):
        raise ValueError("publication payload must be an object")
    payload = deepcopy(dispatch.payload_snapshot)
    expected = dispatch.payload_sha256
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("approved payload hash is invalid")
    try:
        actual = payload_sha256(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("publication payload is not canonical JSON") from exc
    if not hmac.compare_digest(actual, expected):
        raise ValueError("approved payload hash mismatch")
    return payload


def publish_revision_ref(payload: dict[str, object]) -> str:
    ref = payload.get("manuscript_ref")
    number = payload.get("revision_no")
    if not isinstance(ref, str) or not ART.fullmatch(ref):
        raise ValueError("publication manuscript reference mismatch")
    if type(number) is not int or number < 1:
        raise ValueError("publication revision number is invalid")
    revision_ref = f"{ref}-R{number:02d}"
    if payload.get("revision_ref") != revision_ref:
        raise ValueError("publication revision reference mismatch")
    if (payload.get("schema_version") != "confluence.publication.v1"
            or payload.get("destination_key") != "confluence"
            or payload.get("visibility") != "public"):
        raise ValueError("publication candidate policy mismatch")
    return revision_ref


def withdrawal_manuscript_ref(payload: dict[str, object]) -> str:
    if set(payload) != UNPUBLISH_FIELDS or payload.get("operation_kind") != "unpublish":
        raise ValueError("canonical unpublish payload required")
    destination_ref = payload.get("destination_ref")
    if not isinstance(destination_ref, str) or not destination_ref.startswith("confluence:"):
        raise ValueError("unpublish destination reference mismatch")
    ref = destination_ref.removeprefix("confluence:")
    if not ART.fullmatch(ref):
        raise ValueError("unpublish manuscript reference mismatch")
    return ref


def check_resolved_identity(dispatch, selected, payload, *, site_base_url: str) -> None:
    if selected.manuscript_id != dispatch.manuscript_id:
        raise ValueError("publication manuscript identity changed")
    if selected.revision_id != dispatch.revision_id:
        raise ValueError("publication revision identity changed")
    if payload.get("destination_ref") != f"confluence:{selected.manuscript_ref}":
        raise ValueError("publication destination reference changed")
    expected_url = _route(site_base_url, selected.locale, selected.manuscript_ref)
    if payload.get("destination_url") != expected_url:
        raise ValueError("publication destination URL changed")
    if dispatch.action == "publish":
        for field in ("manuscript_ref", "revision_ref", "revision_no", "locale", "edition_ref"):
            if payload.get(field) != getattr(selected, field):
                raise ValueError("publication selected revision fields changed")
    else:
        value = payload.get("published_revision_id")
        try:
            revision_id = UUID(value) if isinstance(value, str) else None
        except ValueError as exc:
            raise ValueError("unpublish published revision is invalid") from exc
        if revision_id != dispatch.revision_id:
            raise ValueError("unpublish published revision identity changed")
