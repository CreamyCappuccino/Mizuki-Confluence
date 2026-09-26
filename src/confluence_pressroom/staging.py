"""Private filesystem staging projection with deterministic readback."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .payload import payload_sha256
from .staging_readback import article_matches, mismatched_surfaces
from .static_pages import ROBOTS, render_article, render_browse, render_index, render_search, route_path

ART = re.compile(r"ART[0-9]{4,}\Z")


@dataclass(frozen=True, slots=True)
class StageReceipt:
    action: str
    manuscript_ref: str
    revision_ref: str
    destination_ref: str
    destination_url: str
    payload_sha256: str


@dataclass(frozen=True, slots=True)
class StageLookup:
    outcome: str
    destination_ref: str | None = None
    destination_url: str | None = None
    error_code: str | None = None
    error_summary: str | None = None


class PrivateStagingStore:
    """Private output root; no external transport or production registry mutation."""

    def __init__(self, root: str | Path) -> None:
        path = Path(root).expanduser()
        if not path.is_absolute():
            raise ValueError("staging root must be absolute")
        self.root = path.resolve()
        self.site = self.root / "site"
        self.state_file = self.root / "state.json"
        self.ops = self.root / "operations"

    def publish(self, payload: dict[str, object], *, idempotency_key: str) -> StageReceipt:
        self._validate_publish_payload(payload)
        digest = payload_sha256(payload)
        prior = self._read_operation(idempotency_key)
        if prior is not None:
            self._assert_same_operation(prior, "publish", digest)
            if self.lookup("publish", payload).outcome != "succeeded":
                raise RuntimeError("idempotent publish receipt exists but readback differs")
            return self._receipt_from_operation(prior)

        state = self._load_state()
        ref = str(payload["manuscript_ref"])
        state["articles"][ref] = payload
        state["history"][ref] = {
            "revision_ref": payload["revision_ref"],
            "published_on": payload["published_on"],
            "destination_ref": payload["destination_ref"],
            "destination_url": payload["destination_url"],
        }
        self._write_projection(state)
        lookup = self.lookup("publish", payload)
        if lookup.outcome != "succeeded":
            raise RuntimeError(f"staging publish readback failed: {lookup.error_code}")
        receipt = self._receipt("publish", payload, digest)
        self._write_operation_receipt(idempotency_key, receipt)
        return receipt

    def unpublish(self, payload: dict[str, object], *, idempotency_key: str) -> StageReceipt:
        ref = self._validate_unpublish_payload(payload)
        digest = payload_sha256(payload)
        prior = self._read_operation(idempotency_key)
        if prior is not None:
            self._assert_same_operation(prior, "unpublish", digest)
            if self.lookup("unpublish", payload).outcome != "succeeded":
                raise RuntimeError("idempotent unpublish receipt exists but readback differs")
            return self._receipt_from_operation(prior)

        state = self._load_state()
        published = state["articles"].get(ref)
        if not isinstance(published, dict):
            raise ValueError("Confluence staging article is not currently published")
        state["articles"].pop(ref, None)
        self._write_projection(state)
        lookup = self.lookup("unpublish", payload)
        if lookup.outcome != "succeeded":
            raise RuntimeError(f"staging unpublish readback failed: {lookup.error_code}")
        receipt = self._receipt("unpublish", published, digest)
        self._write_operation_receipt(idempotency_key, receipt)
        return receipt

    def lookup(self, action: str, payload: dict[str, object]) -> StageLookup:
        try:
            return self._lookup(action, payload)
        except OSError:
            return StageLookup("unknown", error_code="readback_unavailable",
                               error_summary="staging readback could not be read")

    def _lookup(self, action: str, payload: dict[str, object]) -> StageLookup:
        state = self._load_state()
        articles = state["articles"]
        if action == "unpublish":
            ref = self._validate_unpublish_payload(payload)
            article = self._article_path_from_url(str(payload["destination_url"]), ref)
            if (ref in articles or article.exists()
                    or mismatched_surfaces(self.site, articles)):
                return StageLookup("failed", error_code="artifact_or_listing_still_exists",
                                   error_summary="withdrawal body or individual surfaces differ")
            if (self.site / "sitemap.xml").exists():
                return StageLookup("failed", error_code="sitemap_present",
                                   error_summary="sitemap must not be generated")
            return StageLookup("succeeded", str(payload["destination_ref"]), str(payload["destination_url"]))
        if action != "publish":
            raise ValueError("unsupported staging lookup action")

        self._validate_publish_payload(payload)
        article = self._article_path(payload)
        ref = str(payload["manuscript_ref"])
        if not article.exists():
            return StageLookup("failed", error_code="artifact_missing", error_summary="article missing")
        if not article_matches(article, payload):
            return StageLookup("failed", error_code="artifact_mismatch",
                               error_summary="complete article artifact differs from approved candidate")
        stored = articles.get(ref)
        if (not isinstance(stored, dict) or payload_sha256(stored) != payload_sha256(payload)
                or mismatched_surfaces(self.site, articles)):
            return StageLookup("failed", error_code="listing_missing",
                               error_summary="published projection or individual discovery surfaces differ")
        if (self.site / "sitemap.xml").exists():
            return StageLookup("failed", error_code="sitemap_present", error_summary="sitemap must not be generated")
        return StageLookup("succeeded", str(payload["destination_ref"]), str(payload["destination_url"]))

    def publication_identity(self, manuscript_ref: str) -> dict[str, object] | None:
        state = self._load_state()
        value = state["articles"].get(manuscript_ref) or state["history"].get(manuscript_ref)
        if not isinstance(value, dict):
            return None
        return {field: value.get(field) for field in
                ("revision_ref", "destination_ref", "destination_url")}

    def check_operation_identity(self, action: str, payload: dict[str, object], *, idempotency_key: str) -> None:
        prior = self._read_operation(idempotency_key)
        if prior is not None:
            self._assert_same_operation(prior, action, payload_sha256(payload))

    def published_payload(self, manuscript_ref: str) -> dict[str, object] | None:
        value = self._load_state()["articles"].get(manuscript_ref)
        return dict(value) if isinstance(value, dict) else None

    def published_on(self, manuscript_ref: str) -> str | None:
        state = self._load_state()
        current = state["articles"].get(manuscript_ref)
        if isinstance(current, dict) and isinstance(current.get("published_on"), str):
            return current["published_on"]
        history = state["history"].get(manuscript_ref)
        if isinstance(history, dict) and isinstance(history.get("published_on"), str):
            return history["published_on"]
        return None

    def _load_state(self) -> dict[str, object]:
        if not self.state_file.exists():
            return {"schema_version": "confluence.staging.v1", "articles": {}, "history": {}}
        value = json.loads(self.state_file.read_text(encoding="utf-8"))
        if value.get("schema_version") != "confluence.staging.v1" or not isinstance(value.get("articles"), dict):
            raise ValueError("staging state schema mismatch")
        value.setdefault("history", {})
        if not isinstance(value["history"], dict):
            raise ValueError("staging history schema mismatch")
        return value

    def _write_projection(self, state: dict[str, object]) -> None:
        articles = dict(state["articles"])
        self.site.mkdir(parents=True, exist_ok=True)
        expected: set[Path] = set()
        for payload in articles.values():
            path = self._article_path(payload)
            expected.add(path)
            self._write_text(path, render_article(payload, payload_sha256(payload)))
        for path in self.site.rglob("art*.html"):
            if "/articles/" in path.as_posix() and path not in expected:
                path.unlink(missing_ok=True)
        self._write_text(self.site / "index.html", render_index(articles))
        self._write_text(self.site / "browse.html", render_browse(articles))
        self._write_text(self.site / "search.json", render_search(articles))
        (self.site / "sitemap.xml").unlink(missing_ok=True)
        self._write_json(self.state_file, state)

    def _article_path(self, payload: dict[str, object]) -> Path:
        ref = str(payload["manuscript_ref"])
        return self._article_path_from_url(str(payload["destination_url"]), ref)

    def _article_path_from_url(self, destination_url: str, manuscript_ref: str) -> Path:
        dummy = {"manuscript_ref": manuscript_ref, "locale": "ja", "destination_url": destination_url}
        # route_path validates locale from the payload, so recover it from the URL suffix first.
        match = re.search(r"/(ja|en)/articles/(art[0-9]+)\.html$", destination_url)
        if match is None or match.group(2).upper() != manuscript_ref:
            raise ValueError("unpublish destination_url does not match Confluence route")
        dummy["locale"] = match.group(1)
        return self.site.joinpath(*route_path(dummy).split("/"))

    def _validate_publish_payload(self, payload: dict[str, object]) -> None:
        if payload.get("destination_key") != "confluence" or payload.get("visibility") != "public":
            raise ValueError("staging accepts only Confluence Phase 1 public candidates")
        ref = payload.get("manuscript_ref")
        if not isinstance(ref, str) or not ART.fullmatch(ref):
            raise ValueError("invalid manuscript_ref")
        if not isinstance(payload.get("rendered_html"), str) or not payload["rendered_html"]:
            raise ValueError("prepared rendered_html is required")
        if not isinstance(payload.get("category_paths"), list) or not isinstance(payload.get("tags"), list):
            raise ValueError("taxonomy arrays required")
        self._article_path(payload)

    def _validate_unpublish_payload(self, payload: dict[str, object]) -> str:
        if payload.get("operation_kind") != "unpublish":
            raise ValueError("unpublish operation_kind required")
        destination_ref = payload.get("destination_ref")
        if not isinstance(destination_ref, str) or not destination_ref.startswith("confluence:ART"):
            raise ValueError("invalid Confluence unpublish destination_ref")
        ref = destination_ref.split(":", 1)[1]
        if not ART.fullmatch(ref):
            raise ValueError("invalid Confluence unpublish manuscript identity")
        if not isinstance(payload.get("published_revision_id"), str) or not payload["published_revision_id"]:
            raise ValueError("published_revision_id required")
        self._article_path_from_url(str(payload.get("destination_url") or ""), ref)
        return ref

    def _receipt(self, action: str, payload: dict[str, object], digest: str) -> StageReceipt:
        return StageReceipt(action, str(payload["manuscript_ref"]), str(payload["revision_ref"]), str(payload["destination_ref"]), str(payload["destination_url"]), digest)

    def _operation_path(self, key: str) -> Path:
        if not isinstance(key, str) or not key:
            raise ValueError("idempotency key required")
        return self.ops / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def _read_operation(self, key: str) -> dict[str, object] | None:
        path = self._operation_path(key)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _write_operation_receipt(self, key: str, receipt: StageReceipt) -> None:
        self._write_json(self._operation_path(key), {
            "action": receipt.action, "payload_sha256": receipt.payload_sha256,
            "manuscript_ref": receipt.manuscript_ref, "revision_ref": receipt.revision_ref,
            "destination_ref": receipt.destination_ref, "destination_url": receipt.destination_url,
        })

    def _receipt_from_operation(self, prior: dict[str, object]) -> StageReceipt:
        return StageReceipt(str(prior["action"]), str(prior["manuscript_ref"]), str(prior["revision_ref"]), str(prior["destination_ref"]), str(prior["destination_url"]), str(prior["payload_sha256"]))

    def _assert_same_operation(self, prior: dict[str, object], action: str, digest: str) -> None:
        if prior.get("action") != action or prior.get("payload_sha256") != digest:
            raise ValueError("idempotency key was already used for different input")

    def _write_json(self, path: Path, value: dict[str, object]) -> None:
        self._write_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

    def _write_text(self, path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
                handle.write(value); handle.flush(); os.fsync(handle.fileno()); temporary = Path(handle.name)
            os.replace(temporary, path); temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
