"""Prepare public-safe data from an exact Pressroom revision; no editorial writes."""
from .config import ConfluenceError, RehearsalConfig
from .html_prepare import POLICY_VERSION, prepare_html
from .payload_schema import validate_payload
from .ports import ResolvedManuscript

AUTHOR_FIELDS = ("author_ref", "persona_name", "harness", "model", "role", "provenance_source")
METADATA_FIELDS = {"published_on", "visibility"}


def prepare_payload(resolved: ResolvedManuscript, metadata: dict | None,
                    config: RehearsalConfig, previous: dict | None = None) -> dict:
    """Before PUB only. In particular, ignore all AIL snapshot publication state."""
    if metadata is not None and not isinstance(metadata, dict):
        raise ConfluenceError("destination metadata must be an object")
    meta = dict(metadata or {})
    if set(meta) - METADATA_FIELDS or meta.get("visibility", "public") != "public":
        raise ConfluenceError("unsupported destination metadata/visibility")
    snapshot = resolved.snapshot
    if previous is not None:
        validate_payload(previous, site_base_url=config.site_base_url)
        if previous["manuscript_ref"] != snapshot.manuscript_ref:
            raise ConfluenceError("prior publication belongs to another manuscript")
    day = meta.get("published_on")
    if day is None and previous is not None:
        day = previous["published_on"]
    if day is None:
        raise ConfluenceError("first preparation needs destination_metadata.published_on")
    if previous is not None and previous["locale"] != snapshot.locale:
        raise ConfluenceError("locale/route change requires an explicit migration")
    authors = [{key: getattr(author, key) for key in AUTHOR_FIELDS}
               for author in snapshot.authors]
    payload = {
        "schema_version": "confluence.publication.v1", "destination_key": "confluence",
        "manuscript_ref": snapshot.manuscript_ref, "revision_ref": snapshot.revision_ref,
        "revision_no": snapshot.revision_no, "edition_ref": snapshot.edition_ref,
        "locale": snapshot.locale, "destination_ref": f"confluence:{snapshot.manuscript_ref}",
        "destination_url": config.url(snapshot.manuscript_ref, snapshot.locale),
        "title": snapshot.title, "excerpt": snapshot.excerpt,
        "rendered_html": prepare_html(snapshot.rendered_html),
        "renderer_version": f"{snapshot.renderer_version}|{POLICY_VERSION}",
        "author_label": snapshot.author_label, "authors": authors,
        "category_paths": [list(p) for p in snapshot.category_paths],
        "tags": list(snapshot.tags), "published_on": day,
        "content_updated_at": (snapshot.content_updated_at.isoformat()
                               if snapshot.content_updated_at is not None else None),
        "visibility": "public",
    }
    validate_payload(payload, site_base_url=config.site_base_url)
    return payload
