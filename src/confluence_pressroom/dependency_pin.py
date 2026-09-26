"""Read and validate the real-renderer handoff provenance.

This records a rehearsal source identity. It is not deployed-runtime attestation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

SCHEMA = "confluence.renderer-fixture.v1"


@dataclass(frozen=True, slots=True)
class DependencyPin:
    pressroom_commit: str
    md_converter_commit: str
    renderer_version: str
    dependencies: dict[str, str]

    @property
    def reproducible_locator(self) -> str:
        return f"pressroom:{self.pressroom_commit}/md-converter:{self.md_converter_commit}"


def load_dependency_pin(path: str | Path) -> DependencyPin:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != SCHEMA or value.get("synthetic_only") is not True:
        raise ValueError("unsupported renderer provenance")
    if value.get("stage") != "raw_pressroom_renderer_not_prepared_payload":
        raise ValueError("renderer provenance stage mismatch")
    pressroom = value.get("pressroom")
    converter = value.get("md_converter")
    dependencies = value.get("dependencies")
    if not isinstance(pressroom, dict) or not isinstance(converter, dict):
        raise ValueError("renderer provenance source identity missing")
    if not isinstance(dependencies, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v for k, v in dependencies.items()
    ):
        raise ValueError("renderer dependency versions missing")
    pcommit = pressroom.get("commit")
    ccommit = converter.get("commit")
    renderer = value.get("renderer_version")
    for field, item in (
        ("pressroom commit", pcommit),
        ("md-converter commit", ccommit),
        ("renderer_version", renderer),
    ):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field} missing")
    return DependencyPin(
        pressroom_commit=pcommit,
        md_converter_commit=ccommit,
        renderer_version=renderer,
        dependencies=dict(dependencies),
    )
