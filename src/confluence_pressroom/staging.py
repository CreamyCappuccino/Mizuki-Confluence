"""Private filesystem staging projection with deterministic readback."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .payload import payload_sha256

ART = re.compile(r"ART[0-9]{4,}\Z")
ROBOTS = "noindex, nofollow, noarchive"


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
    """A private, explicit output root. Nothing is published to the network here."""

    def __init__(self, root: str | Path) -> None:
        path = Path(root).expanduser()
        if not path.is_absolute():
            raise ValueError("staging root must be absolute")
        self.root = path.resolve()
        self.site = self.root / "site"
        self.state_file = self.root / "state.json"
        self.ops = self.root / "operations"

    def publish(self, payload: dict[str, object], *, idempotency_key: str) -> StageReceipt:
        self._validate_payload(payload)
        digest = payload_sha256(payload)
        prior = self._read_operation(idempotency_key)
        if prior is not None:
            self._assert_same_operation(prior, "publish", digest)
            lookup = self.lookup("publish", payload)
            if lookup.outcome != "succeeded":
                raise RuntimeError("idempotent publish receipt exists but readback differs")
            return self._receipt("publish", payload, digest)

        state = self._load_state()
        state["articles"][payload["manuscript_ref"]] = payload
        self._write_projection(state)
        lookup = self.lookup("publish", payload)
        if lookup.outcome != "succeeded":
            raise RuntimeError(f"staging publish readback failed: {lookup.error_code}")
        self._write_operation(idempotency_key, "publish", digest, payload)
        return self._receipt("publish", payload, digest)

    def unpublish(self, payload: dict[str, object], *, idempotency_key: str) -> StageReceipt:
        self._validate_payload(payload)
        digest = payload_sha256(payload)
        prior = self._read_operation(idempotency_key)
        if prior is not None:
            self._assert_same_operation(prior, "unpublish", digest)
            lookup = self.lookup("unpublish", payload)
            if lookup.outcome != "succeeded":
                raise RuntimeError("idempotent unpublish receipt exists but readback differs")
            return self._receipt("unpublish", payload, digest)

        state = self._load_state()
        state["articles"].pop(payload["manuscript_ref"], None)
        self._write_projection(state)
        lookup = self.lookup("unpublish", payload)
        if lookup.outcome != "succeeded":
            raise RuntimeError(f"staging unpublish readback failed: {lookup.error_code}")
        self._write_operation(idempotency_key, "unpublish", digest, payload)
        return self._receipt("unpublish", payload, digest)

    def lookup(self, action: str, payload: dict[str, object]) -> StageLookup:
        self._validate_payload(payload)
        article = self._article_path(payload)
        ref = str(payload["destination_ref"])
        url = str(payload["destination_url"])
        listed = self._listed(payload)
        if action == "unpublish":
            if not article.exists() and not listed:
                return StageLookup("succeeded", ref, url)
            return StageLookup(
                "failed", error_code="artifact_or_listing_still_exists",
                error_summary="withdrawn article remains readable or listed",
            )
        if action != "publish":
            raise ValueError("unsupported staging lookup action")
        if not article.exists():
            return StageLookup("failed", error_code="artifact_missing", error_summary="article missing")
        text = article.read_text(encoding="utf-8")
        digest = payload_sha256(payload)
        markers = (
            f'data-manuscript-ref="{escape(str(payload["manuscript_ref"]), quote=True)}"',
            f'data-revision-ref="{escape(str(payload["revision_ref"]), quote=True)}"',
            f'content="{digest}"',
            f'<meta name="robots" content="{ROBOTS}">',
        )
        if not all(marker in text for marker in markers):
            return StageLookup("failed", error_code="artifact_mismatch", error_summary="article markers differ")
        if not listed:
            return StageLookup("failed", error_code="listing_missing", error_summary="published article is not listed")
        if (self.site / "sitemap.xml").exists():
            return StageLookup("failed", error_code="sitemap_present", error_summary="sitemap must not be generated")
        return StageLookup("succeeded", ref, url)

    def _load_state(self) -> dict[str, object]:
        if not self.state_file.exists():
            return {"schema_version": "confluence.staging.v1", "articles": {}}
        value = json.loads(self.state_file.read_text(encoding="utf-8"))
        if value.get("schema_version") != "confluence.staging.v1" or not isinstance(value.get("articles"), dict):
            raise ValueError("staging state schema mismatch")
        return value

    def _write_projection(self, state: dict[str, object]) -> None:
        articles = dict(state["articles"])
        self.site.mkdir(parents=True, exist_ok=True)
        expected: set[Path] = set()
        for payload in articles.values():
            path = self._article_path(payload)
            expected.add(path)
            self._write_text(path, self._render_article(payload))
        articles_root = self.site
        for path in articles_root.glob("*/articles/art*.html"):
            if path not in expected:
                path.unlink(missing_ok=True)
        self._write_text(self.site / "index.html", self._render_index(articles))
        self._write_text(self.site / "browse.html", self._render_browse(articles))
        search = [self._search_entry(p) for p in self._sorted_articles(articles)]
        self._write_text(self.site / "search.json", json.dumps(search, ensure_ascii=False, indent=2) + "\n")
        (self.site / "sitemap.xml").unlink(missing_ok=True)
        self._write_json(self.state_file, state)

    def _render_shell(self, title: str, body: str) -> str:
        return (
            '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            f'<meta name="robots" content="{ROBOTS}"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title></head><body>{body}</body></html>'
        )

    def _render_article(self, payload: dict[str, object]) -> str:
        digest = payload_sha256(payload)
        author = payload.get("author_label") or ""
        categories = " / ".join(" › ".join(path) for path in payload["category_paths"])
        tags = " ".join(f"#{tag}" for tag in payload["tags"])
        body = (
            f'<main class="reading-article" data-manuscript-ref="{escape(str(payload["manuscript_ref"]), quote=True)}" '
            f'data-revision-ref="{escape(str(payload["revision_ref"]), quote=True)}">'
            f'<meta name="confluence-payload-sha256" content="{digest}">'
            f'<a href="../../../index.html">← Confluence</a>'
            f'<header><p>{escape(categories)}</p><h1>{escape(str(payload["title"]))}</h1>'
            f'<p>{escape(str(author))} · <time>{escape(str(payload["published_on"]))}</time></p></header>'
            f'<article>{payload["rendered_html"]}</article>'
            f'<footer><p>{escape(tags)}</p></footer></main>'
        )
        return self._render_shell(str(payload["title"]), body)

    def _render_index(self, articles: dict[str, object]) -> str:
        rows = []
        for payload in self._sorted_articles(articles):
            path = self._relative_article_url(payload)
            rows.append(
                f'<article data-manuscript-ref="{escape(str(payload["manuscript_ref"]), quote=True)}">'
                f'<h2><a href="{path}">{escape(str(payload["title"]))}</a></h2>'
                f'<p>{escape(str(payload.get("excerpt") or ""))}</p>'
                f'<small>{escape(str(payload.get("author_label") or ""))} · {escape(str(payload["published_on"]))}</small></article>'
            )
        return self._render_shell("Confluence staging", '<main><h1>Confluence</h1>' + "".join(rows) + "</main>")

    def _render_browse(self, articles: dict[str, object]) -> str:
        categories: dict[str, int] = {}
        tags: dict[str, int] = {}
        for payload in articles.values():
            for path in payload["category_paths"]:
                label = " › ".join(path)
                categories[label] = categories.get(label, 0) + 1
            for tag in payload["tags"]:
                tags[tag] = tags.get(tag, 0) + 1
        cat = "".join(f"<li>{escape(k)} <span>{v}</span></li>" for k, v in sorted(categories.items()))
        tag = "".join(f"<li>#{escape(k)} <span>{v}</span></li>" for k, v in sorted(tags.items()))
        return self._render_shell("Browse — Confluence", f"<main><h1>Browse</h1><ul>{cat}</ul><ul>{tag}</ul></main>")

    def _listed(self, payload: dict[str, object]) -> bool:
        ref = str(payload["manuscript_ref"])
        index = self.site / "index.html"
        search = self.site / "search.json"
        browse = self.site / "browse.html"
        if not (index.exists() and search.exists() and browse.exists()):
            return False
        if f'data-manuscript-ref="{ref}"' not in index.read_text(encoding="utf-8"):
            return False
        try:
            items = json.loads(search.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        if not any(item.get("manuscript_ref") == ref for item in items):
            return False
        browse_text = browse.read_text(encoding="utf-8")
        return all(
            escape(" › ".join(path)) in browse_text for path in payload["category_paths"]
        ) and all(f"#{escape(tag)}" in browse_text for tag in payload["tags"])

    def _sorted_articles(self, articles: dict[str, object]) -> list[dict[str, object]]:
        return sorted(articles.values(), key=lambda p: (str(p["published_on"]), str(p["manuscript_ref"])), reverse=True)

    def _search_entry(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "manuscript_ref": payload["manuscript_ref"],
            "revision_ref": payload["revision_ref"],
            "title": payload["title"],
            "excerpt": payload.get("excerpt"),
            "author_label": payload.get("author_label"),
            "published_on": payload["published_on"],
            "category_paths": payload["category_paths"],
            "tags": payload["tags"],
            "url": self._relative_article_url(payload),
        }

    def _relative_article_url(self, payload: dict[str, object]) -> str:
        return f'{payload["locale"]}/articles/{str(payload["manuscript_ref"]).lower()}.html'

    def _article_path(self, payload: dict[str, object]) -> Path:
        ref = str(payload["manuscript_ref"])
        if not ART.fullmatch(ref):
            raise ValueError("invalid manuscript_ref for staging path")
        locale = str(payload["locale"])
        if locale not in {"ja", "en"}:
            raise ValueError("invalid locale for staging path")
        return self.site / locale / "articles" / f"{ref.lower()}.html"

    def _validate_payload(self, payload: dict[str, object]) -> None:
        if payload.get("destination_key") != "confluence" or payload.get("visibility") != "public":
            raise ValueError("staging accepts only Confluence Phase 1 public candidates")
        if not isinstance(payload.get("rendered_html"), str) or not payload["rendered_html"]:
            raise ValueError("prepared rendered_html is required")
        if not isinstance(payload.get("category_paths"), list) or not isinstance(payload.get("tags"), list):
            raise ValueError("taxonomy arrays required")
        self._article_path(payload)

    def _receipt(self, action: str, payload: dict[str, object], digest: str) -> StageReceipt:
        return StageReceipt(
            action=action,
            manuscript_ref=str(payload["manuscript_ref"]),
            revision_ref=str(payload["revision_ref"]),
            destination_ref=str(payload["destination_ref"]),
            destination_url=str(payload["destination_url"]),
            payload_sha256=digest,
        )

    def _operation_path(self, key: str) -> Path:
        if not isinstance(key, str) or not key:
            raise ValueError("idempotency key required")
        return self.ops / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def _read_operation(self, key: str) -> dict[str, object] | None:
        path = self._operation_path(key)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _write_operation(self, key: str, action: str, digest: str, payload: dict[str, object]) -> None:
        self._write_json(self._operation_path(key), {
            "action": action,
            "payload_sha256": digest,
            "manuscript_ref": payload["manuscript_ref"],
            "revision_ref": payload["revision_ref"],
        })

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
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
