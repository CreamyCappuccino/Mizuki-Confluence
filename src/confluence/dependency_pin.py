"""Read-only local checkout/runtime gate. Never fetches, installs, or falls back.

The provenance file is reviewed configuration, not a remote-install recipe.
Passing proves this observation only; it is not deployment/publication authority.
"""
from dataclasses import dataclass
import hashlib
import importlib
from importlib.metadata import version, PackageNotFoundError
import inspect
import json
import os
from pathlib import Path
import platform
import subprocess
from lxml import etree
from .config import ConfluenceError, PRESSROOM_COMMIT
from .html_policy import LXML_VERSION, LIBXML_VERSION

CONVERTER_COMMIT = "0d98198dd2da1abf82e4cf17c1bf8658027f021c"


@dataclass(frozen=True)
class DependencyEvidence:
    pressroom_commit: str
    converter_commit: str
    renderer_version: str
    python_version: str


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), "-c", "core.fsmonitor=false", *args],
            env=env, capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfluenceError("dependency checkout cannot be inspected") from exc
    if result.returncode:
        raise ConfluenceError("dependency checkout inspection failed")
    return result.stdout.strip()


def _checkout(root: Path, commit: str, tree_path: str, expected_tree: str):
    if not root.is_dir() or _git(root, "rev-parse", "HEAD") != commit:
        raise ConfluenceError("dependency checkout revision mismatch")
    if _git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ConfluenceError("dependency checkout has unreviewed changes")
    if _git(root, "rev-parse", f"HEAD:{tree_path}") != expected_tree:
        raise ConfluenceError("dependency package tree mismatch")


def verify_local_dependencies(provenance: Path, pressroom_root: Path,
                              converter_root: Path) -> DependencyEvidence:
    """Explicit roots; no environment-variable paths or older GitHub fallback."""
    try:
        pin = json.loads(Path(provenance).read_text(encoding="utf-8"))
        p, c = pin["pressroom"], pin["md_converter"]
        if (pin["synthetic_only"] is not True or p["commit"] != PRESSROOM_COMMIT
                or c["commit"] != CONVERTER_COMMIT):
            raise ConfluenceError("unreviewed dependency provenance")
        pr, cr = Path(pressroom_root).resolve(), Path(converter_root).resolve()
        _checkout(pr, p["commit"], "src/pressroom/rendering", p["rendering_tree_git_sha1"])
        _checkout(cr, c["commit"], "packages/md-converter", c["package_tree_git_sha1"])
        if _sha(pr / "uv.lock") != p["uv_lock_sha256"]:
            raise ConfluenceError("Pressroom lock identity mismatch")
        if platform.python_version() != pin["python_version"]:
            raise ConfluenceError("rehearsal Python version differs from recorded renderer")
        if etree.LXML_VERSION[:3] != LXML_VERSION or etree.LIBXML_VERSION != LIBXML_VERSION:
            raise ConfluenceError("Confluence HTML parser pin mismatch")
        for name, expected in pin["dependencies"].items():
            if version(name) != expected:
                raise ConfluenceError("renderer dependency version mismatch")
        renderer = importlib.import_module("pressroom.rendering.markdown_renderer").MarkdownRenderer
        converter = importlib.import_module("md_converter")
        source = Path(inspect.getfile(renderer)).resolve()
        expected_source = pr / "src/pressroom/rendering/markdown_renderer.py"
        package = cr / "packages/md-converter"
        if (source != expected_source or Path(converter.__file__).resolve() !=
                package / "src/md_converter/__init__.py"):
            raise ConfluenceError("runtime imported a different dependency checkout")
        if _sha(source) != p["renderer_source_sha256"]:
            raise ConfluenceError("Pressroom renderer source mismatch")
        sources = {x.relative_to(package).as_posix(): _sha(x)
                   for x in sorted((package / "src/md_converter").glob("*.py"))}
        if sources != c["source_sha256"]:
            raise ConfluenceError("converter source hashes mismatch")
        return DependencyEvidence(p["commit"], c["commit"], pin["renderer_version"], pin["python_version"])
    except (OSError, ImportError, PackageNotFoundError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ConfluenceError):
            raise
        raise ConfluenceError("dependency pin unavailable or incomplete; no fallback used") from exc
