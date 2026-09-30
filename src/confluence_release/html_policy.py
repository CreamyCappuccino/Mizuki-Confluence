"""Read an explicit operator-owned HTML verification profile, not provider data."""
from __future__ import annotations

from dataclasses import fields
import json
import os
from pathlib import Path
import stat

from confluence_pressroom.here_now_html import HereNowHtmlPolicy

MAX_POLICY_BYTES = 16_384


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate HTML policy field')
        result[key] = value
    return result


def load_html_policy(path: Path) -> HereNowHtmlPolicy:
    """Load once; do not follow a symlink or expose metadata/secrets in errors."""
    descriptor = os.open(path.expanduser(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError('HTML policy must be an owner-owned 0600 regular file')
        raw = stream.read(MAX_POLICY_BYTES + 1)
    if len(raw) > MAX_POLICY_BYTES:
        raise ValueError('HTML policy exceeds size bound')
    values = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
    required = {'format', 'here_now_base', 'nor_base', 'title', 'description'}
    allowed = {field.name for field in fields(HereNowHtmlPolicy)}
    if not isinstance(values, dict) or not required <= values.keys() or values.keys() - allowed:
        raise ValueError('invalid HTML policy fields')
    return HereNowHtmlPolicy(**values)
