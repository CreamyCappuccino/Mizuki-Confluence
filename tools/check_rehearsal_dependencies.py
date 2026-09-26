#!/usr/bin/env python3
"""Check explicit local dependency roots; no install, Git fetch, DB or writes."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from confluence.config import ConfluenceError
from confluence.dependency_pin import verify_local_dependencies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pressroom", required=True, type=Path)
    parser.add_argument("--converter", required=True, type=Path)
    args = parser.parse_args()
    try:
        e = verify_local_dependencies(
            ROOT / "tests/fixtures/confluence/renderer/provenance.json",
            args.pressroom, args.converter,
        )
    except ConfluenceError as exc:
        print(f"dependency-pin: blocked | {exc}")
        print("No fetch/install/fallback or publication attempted.")
        return 1
    print(f"dependency-pin: verified locally | Pressroom {e.pressroom_commit[:12]}")
    print(f"converter: {e.converter_commit[:12]} | no live publication performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
