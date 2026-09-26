"""Pure static-page rendering for Confluence private rehearsal output."""
from __future__ import annotations

from html import escape
import json
from urllib.parse import urlsplit

ROBOTS = "noindex, nofollow, noarchive"


def route_path(payload: dict[str, object]) -> str:
    """Return the safe site-relative route pinned in destination_url."""
    ref = str(payload["manuscript_ref"])
    locale = str(payload["locale"])
    parts = urlsplit(str(payload["destination_url"]))
    if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment:
        raise ValueError("destination_url must be normalized HTTPS")
    if "%" in parts.path or "\\" in parts.path:
        raise ValueError("destination_url path must not be encoded or contain backslashes")
    segments = [value for value in parts.path.split("/") if value]
    if any(value in {".", ".."} for value in segments):
        raise ValueError("destination_url path traversal is not allowed")
    expected = [locale, "articles", f"{ref.lower()}.html"]
    if segments[-3:] != expected:
        raise ValueError("destination_url does not end in the Confluence article route")
    return "/".join(segments)


def search_entry(payload: dict[str, object]) -> dict[str, object]:
    return {
        "manuscript_ref": payload["manuscript_ref"],
        "revision_ref": payload["revision_ref"],
        "title": payload["title"],
        "excerpt": payload.get("excerpt"),
        "author_label": payload.get("author_label"),
        "published_on": payload["published_on"],
        "category_paths": payload["category_paths"],
        "tags": payload["tags"],
        "url": route_path(payload),
    }


def render_article(payload: dict[str, object], digest: str) -> str:
    author = payload.get("author_label") or ""
    categories = " / ".join(" › ".join(path) for path in payload["category_paths"])
    tags = " ".join(f"#{tag}" for tag in payload["tags"])
    body = (
        f'<main class="reading-article" data-manuscript-ref="{escape(str(payload["manuscript_ref"]), quote=True)}" '
        f'data-revision-ref="{escape(str(payload["revision_ref"]), quote=True)}" '
        f'data-payload-sha256="{digest}">'
        '<a href="/index.html">← Confluence</a>'
        f'<header><p>{escape(categories)}</p><h1>{escape(str(payload["title"]))}</h1>'
        f'<p>{escape(str(author))} · <time>{escape(str(payload["published_on"]))}</time></p></header>'
        f'<article>{payload["rendered_html"]}</article>'
        f'<footer><p>{escape(tags)}</p></footer></main>'
    )
    return render_shell(str(payload["title"]), body, lang=str(payload["locale"]))


def render_index(articles: dict[str, dict[str, object]]) -> str:
    rows = []
    for payload in sorted_articles(articles):
        rows.append(
            f'<article data-manuscript-ref="{escape(str(payload["manuscript_ref"]), quote=True)}">'
            f'<h2><a href="{escape(route_path(payload), quote=True)}">{escape(str(payload["title"]))}</a></h2>'
            f'<p>{escape(str(payload.get("excerpt") or ""))}</p>'
            f'<small>{escape(str(payload.get("author_label") or ""))} · {escape(str(payload["published_on"]))}</small></article>'
        )
    return render_shell("Confluence staging", '<main><h1>Confluence</h1>' + "".join(rows) + "</main>")


def render_browse(articles: dict[str, dict[str, object]]) -> str:
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
    return render_shell("Browse — Confluence", f"<main><h1>Browse</h1><ul>{cat}</ul><ul>{tag}</ul></main>")


def render_search(articles: dict[str, dict[str, object]]) -> str:
    return json.dumps([search_entry(p) for p in sorted_articles(articles)], ensure_ascii=False, indent=2) + "\n"


def sorted_articles(articles: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        articles.values(),
        key=lambda p: (str(p["published_on"]), str(p["manuscript_ref"])),
        reverse=True,
    )


def render_shell(title: str, body: str, *, lang: str = "ja") -> str:
    return (
        f'<!doctype html><html lang="{escape(lang, quote=True)}"><head><meta charset="utf-8">'
        f'<meta name="robots" content="{ROBOTS}"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)}</title></head><body>{body}</body></html>'
    )
