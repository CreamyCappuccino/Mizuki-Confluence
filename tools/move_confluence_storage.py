#!/usr/bin/env python3
"""Move only the old Confluence store into the EXISTING project; never activate it."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from confluence_release.storage_move import plan_copy, copy_storage, archive_source


def read_receipt(path: Path, expected_sha256: str) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        st = os.fstat(f.fileno())
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or stat.S_IMODE(st.st_mode) != 0o600):
            raise ValueError('copy receipt must be owner0600 regular file')
        raw = f.read(16_000_001)
    if len(raw) > 16_000_000 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('copy receipt digest or size mismatch')
    return json.loads(raw)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('plan', 'copy', 'archive'))
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--project-root', type=Path, required=True)
    p.add_argument('--fingerprint')
    p.add_argument('--receipt', type=Path)
    p.add_argument('--receipt-sha256')
    p.add_argument('--archive', type=Path)
    p.add_argument('--executing-source-sha')
    p.add_argument('--confirm-copy', action='store_true')
    p.add_argument('--confirm-cutover', action='store_true')
    args = p.parse_args(argv)
    try:
        if args.action == 'archive':
            if not (args.confirm_cutover and args.receipt and args.receipt_sha256 and args.archive):
                raise ValueError('archive requires confirmed cutover, copy receipt/digest and exact archive path')
            record = read_receipt(args.receipt, args.receipt_sha256)
            if record['source'] != str(args.source_root) or record['project'] != str(args.project_root):
                raise ValueError('receipt does not match the selected source/project')
            archive_source(record, archive=args.archive, executing_source_sha=args.executing_source_sha)
            print('ARCHIVED | old path absent | original bytes retained in project rollback archive')
            return 0
        if args.action == 'copy':
            if not (args.confirm_copy and args.fingerprint and args.receipt):
                raise ValueError('copy requires reviewed fingerprint, receipt path and --confirm-copy')
            record = copy_storage(args.source_root, args.project_root,
                expected_fingerprint=args.fingerprint, receipt_path=args.receipt)
            print(f"COPIED_NOT_ACTIVATED | receipt SHA256 {record['receipt_sha256']}")
        else:
            record = plan_copy(args.source_root, args.project_root)
            print('PLAN_ONLY | no file/config/JOB changes')
        print(f"Inventory fingerprint: {record['fingerprint']}")
        for move in record['moves']:
            files = [e for e in move['inventory'].values() if e['type']=='file']
            print(f"{move['source']} -> {args.project_root/move['target']} | {len(files)} files | {sum(e['size'] for e in files)} bytes")
        return 0
    except Exception as exc:
        print(f'STOP | {type(exc).__name__} | {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
