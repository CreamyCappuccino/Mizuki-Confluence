"""Read-only fixture integrity and optional real-renderer replay. No DB/network."""

import argparse
import hashlib
import inspect
import json
from importlib.metadata import version
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rerender", action="store_true")
    options = parser.parse_args()
    root = Path(__file__).resolve().parent
    metadata = json.loads(root.joinpath("provenance.json").read_text(encoding="utf-8"))
    source = root.joinpath("input.md").read_bytes()
    expected = root.joinpath("output.html").read_bytes()
    require(metadata["synthetic_only"] is True, "synthetic boundary changed")
    require(sha256(source) == metadata["input_sha256"], "input hash mismatch")
    require(sha256(expected) == metadata["output_sha256"], "output hash mismatch")
    if options.rerender:
        import md_converter

        from pressroom.rendering.markdown_renderer import MarkdownRenderer

        for name, pinned in metadata["dependencies"].items():
            require(version(name) == pinned, f"dependency version mismatch: {name}")
        renderer_source = Path(inspect.getfile(MarkdownRenderer)).read_bytes()
        require(
            sha256(renderer_source) == metadata["pressroom"]["renderer_source_sha256"],
            "Pressroom renderer source mismatch",
        )
        package = Path(md_converter.__file__).resolve().parents[2]
        actual_sources = {
            path.relative_to(package).as_posix(): sha256(path.read_bytes())
            for path in sorted(package.joinpath("src/md_converter").glob("*.py"))
        }
        require(
            actual_sources == metadata["md_converter"]["source_sha256"],
            "md-converter source mismatch",
        )
        rendered = MarkdownRenderer().render(source.decode("utf-8"))
        require(rendered.renderer_version == metadata["renderer_version"], "renderer mismatch")
        require(rendered.html.encode("utf-8") == expected, "real renderer output mismatch")
    mode = "real-renderer byte replay" if options.rerender else "stored byte integrity only"
    print(f"PASS: {mode}; not provider preparation or publication evidence")


if __name__ == "__main__":
    main()
