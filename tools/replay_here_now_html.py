"""Offline byte-evidence replay. Reads files only; no DB, network or publication.

The expected digest must come from the original trusted private BuildReceipt,
not be computed from the remote file. This tool is not a full release acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from confluence_pressroom.release_checksums import DIGEST, MAX_ARTIFACT_FILE_BYTES, safe_relative_path
from confluence_release.html_policy import load_html_policy


def read_bounded(path: Path) -> bytes:
    with path.open('rb') as stream:
        result = stream.read(MAX_ARTIFACT_FILE_BYTES + 1)
    if len(result) > MAX_ARTIFACT_FILE_BYTES:
        raise ValueError('evidence file exceeds readback size bound')
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--original', required=True, type=Path)
    parser.add_argument('--remote', required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--relative', required=True)
    args = parser.parse_args(argv)
    try:
        profile = load_html_policy(args.profile)
        original, remote = read_bounded(args.original), read_bounded(args.remote)
        if (not DIGEST.fullmatch(args.expected_sha256)
                or hashlib.sha256(original).hexdigest() != args.expected_sha256):
            raise ValueError('original does not match the independent receipt digest')
        safe_relative_path(args.relative)
        if not args.relative.lower().endswith(('.html', '.htm')):
            raise ValueError('this replay tool only classifies HTML')
        if args.base not in (profile.here_now_base, profile.nor_base):
            raise ValueError('origin outside pinned profile')
        mode = 'raw-exact'
        if remote != original:
            expected = profile.predict(original, base=args.base, relative=args.relative)
            if remote != expected:
                raise ValueError('remote differs from the single predicted representation')
            mode = profile.format
        print(f'PASS | comparison={mode} | original={args.expected_sha256}')
        print(f'delivered={hashlib.sha256(remote).hexdigest()} | policy={profile.sha256}')
        print('scope: offline file pair only; not JOB completion or full-site acceptance')
        return 0
    except (OSError, ValueError) as exc:
        print(f'STOP | {type(exc).__name__} | check original receipt and pinned profile')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
