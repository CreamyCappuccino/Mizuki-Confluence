#!/usr/bin/env python3
"""Check deterministic preparation from captured real-renderer bytes. No DB/network.

--write updates only the named synthetic prepared fixture, never the raw evidence.
This command does NOT invoke Pressroom's renderer or create a PUB/APR/JOB.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from confluence.config import ConfluenceError, RehearsalConfig
from confluence.payload_schema import payload_sha256
from confluence.ports import ResolvedManuscript
from confluence.preparation import prepare_payload

FIXTURES = ROOT / "tests/fixtures/confluence"
OUTPUT = FIXTURES / "prepared_renderer_v1.json"


def raw_fixture():
    folder = FIXTURES / "renderer"
    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    raw = (folder / "output.html").read_bytes()
    source = (folder / "input.md").read_bytes()
    if (provenance["synthetic_only"] is not True
            or hashlib.sha256(raw).hexdigest() != provenance["output_sha256"]
            or hashlib.sha256(source).hexdigest() != provenance["input_sha256"]):
        raise ConfluenceError("renderer fixture provenance mismatch")
    return raw.decode("utf-8"), provenance


def resolved_fixture():
    """Synthetic stand-in for a selected revision, NEVER a live ART lookup."""
    raw, provenance = raw_fixture()
    seed = json.loads((FIXTURES / "publication_v1.json").read_text(encoding="utf-8"))["payload_snapshot"]
    data = {key: value for key, value in seed.items() if key not in {"rendered_html", "renderer_version"}}
    data.update(rendered_html=raw, renderer_version=provenance["renderer_version"])
    data["authors"] = tuple(SimpleNamespace(**a) for a in data["authors"])
    data["content_updated_at"] = datetime.fromisoformat(data["content_updated_at"])
    data["category_paths"] = tuple(tuple(p) for p in data["category_paths"])
    data["tags"] = tuple(data["tags"])
    return ResolvedManuscript(UUID(int=1), UUID(int=2), SimpleNamespace(**data))


def build_fixture():
    # No filesystem write; this root is solely part of the in-memory config.
    config = RehearsalConfig(Path("/tmp/confluence-fixture-only-not-created"))
    resolved = resolved_fixture()
    payload = prepare_payload(resolved, {"published_on": "2026-09-26"}, config)
    return {"fixture_only": True, "site_base_url": config.site_base_url,
            "site_policy": config.site_policy, "payload_snapshot": payload,
            "expected_payload_sha256": payload_sha256(payload)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        result = build_fixture()
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.write:
            OUTPUT.write_text(encoded, encoding="utf-8")
        elif OUTPUT.read_text(encoding="utf-8") != encoded:
            raise ConfluenceError("prepared fixture differs; review before --write")
        print("PASS: captured renderer -> pre-PUB preparation -> canonical payload")
        print("payload_sha256: " + result["expected_payload_sha256"])
        print("mode: fixture-only | live rerender/DB/PUB/APR/JOB/network: not used")
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print("preparation: rejected | check fixture/policy/version; no publication attempted")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
