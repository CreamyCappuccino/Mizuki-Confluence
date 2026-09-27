"""Adapted from AIL here_now_client.py: prepare, diff upload, finalize, reconcile.

No AIL slug or key is embedded. The site must already exist in the configured
account. Site creation / Nor route provisioning is an operator setup step.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import mimetypes
import os
import re
from pathlib import Path
import stat
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from .artifacts import BuildReceipt, read_files, sha256, verify_local_artifact

API_BASE = 'https://here.now'


class HereNowError(RuntimeError):
    pass


class HereNowOutcomeUnknownError(HereNowError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_here_now_api_key(path: Path | None = None) -> str:
    path = path or Path('~/.herenow/credentials').expanduser()
    if path.is_symlink():
        raise ValueError('here.now credential file must not be a symlink')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('here.now credentials require an owner-only regular file')
    key = ''.join(path.read_text(encoding='utf-8').split())
    if not key:
        raise ValueError('here.now credentials are empty')
    return key


@dataclass(frozen=True)
class HereNowReceipt:
    slug: str
    version_id: str
    uploaded_files: int
    reconciled: bool


def required_text(value: dict, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise HereNowError(f'here.now response is missing {key}')
    return item


def manifest_hashes(details: dict) -> dict[str, str]:
    value = details.get('manifest')
    if not isinstance(value, list):
        raise HereNowError('here.now response has no manifest')
    result = {}
    for item in value:
        if not isinstance(item, dict):
            raise HereNowError('invalid here.now manifest entry')
        path, h = required_text(item, 'path'), required_text(item, 'hash')
        if path in result:
            raise HereNowError('duplicate here.now manifest path')
        result[path] = h
    return result


def validated_finalize_url(slug: str, url: str) -> str:
    p = urlsplit(url)
    expected_path = f'/api/v1/publish/{slug}/finalize'
    if (p.scheme != 'https' or p.netloc != 'here.now' or p.username is not None
            or p.password is not None or p.path != expected_path or p.query or p.fragment):
        raise HereNowError('here.now finalize URL does not match the configured site')
    return url


class HereNowClient:
    def __init__(self, api_key: str, *, opener=None, timeout: float = 30):
        if not api_key.strip():
            raise ValueError('here.now API key is empty')
        self._key = api_key.strip()
        # Do not forward Authorization across a redirect from a finalize URL.
        self._open = opener or build_opener(_NoRedirect()).open
        self._timeout = timeout

    def _request(self, method: str, url: str, payload=None) -> dict:
        p = urlsplit(url)
        if (p.scheme != 'https' or p.netloc != 'here.now' or p.username is not None
                or not p.path.startswith('/api/')):
            raise HereNowError('refusing credentials outside the canonical here.now API')
        body = None if payload is None else json.dumps(payload, separators=(',', ':')).encode()
        req = Request(url, data=body, method=method, headers={
            'Authorization': f'Bearer {self._key}',
            'X-HereNow-Client': 'confluence-release-worker', 'Content-Type': 'application/json'})
        try:
            with self._open(req, timeout=self._timeout) as response:
                value = json.loads(response.read().decode('utf-8'))
        except HTTPError as exc:
            raise HereNowError(f'here.now API HTTP {exc.code}') from exc
        if not isinstance(value, dict) or value.get('error'):
            raise HereNowError('here.now API rejected the request or returned invalid data')
        return value

    def site_details(self, slug: str) -> dict:
        if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
            raise ValueError('invalid here.now slug')
        return self._request('GET', f'{API_BASE}/api/v1/publish/{slug}')

    def publish(self, slug: str, receipt: BuildReceipt) -> HereNowReceipt:
        verify_local_artifact(receipt)
        files = read_files(receipt.output)
        before = self.site_details(slug)
        if manifest_hashes(before) == receipt.checksums:
            return HereNowReceipt(slug, required_text(before, 'currentVersionId'), 0, True)
        prepared = self._request('PUT', f'{API_BASE}/api/v1/publish/{slug}', {
            'files': [dict(path=name, size=len(data), contentType=(mimetypes.guess_type(name)[0]
                         or 'application/octet-stream'), hash=sha256(data))
                      for name, data in sorted(files.items())], 'spaMode': False})
        upload = prepared.get('upload')
        if not isinstance(upload, dict) or not isinstance(upload.get('uploads', []), list):
            raise HereNowError('here.now prepare has invalid uploads')
        version = required_text(upload, 'versionId')
        prepared_slug = prepared.get('slug')
        if prepared_slug is not None and prepared_slug != slug:
            raise HereNowError('here.now prepare target does not match the configured site')
        finalize_url = validated_finalize_url(slug, required_text(upload, 'finalizeUrl'))
        seen = set()
        for entry in upload.get('uploads', []):
            name = required_text(entry, 'path')
            if name not in files or name in seen:
                raise HereNowError('unknown/duplicate requested upload path')
            seen.add(name)
            url = required_text(entry, 'url')
            p = urlsplit(url)
            if p.scheme != 'https' or not p.hostname or p.username is not None:
                raise HereNowError('invalid presigned upload URL')
            ct = (entry.get('headers') or {}).get('Content-Type') or 'application/octet-stream'
            # Presigned storage upload deliberately carries no here.now API key.
            req = Request(url, data=files[name], method='PUT', headers={'Content-Type': ct})
            with self._open(req, timeout=self._timeout) as res:
                if not 200 <= res.status < 300:
                    raise HereNowError('here.now artifact upload failed')
        try:
            finalized = self._request('POST', finalize_url, {'versionId': version})
            finalized_slug = required_text(finalized, 'slug')
            finalized_version = required_text(finalized, 'currentVersionId')
            if finalized_slug != slug:
                raise HereNowError('here.now finalize response changed the configured site')
            if finalized_version != version and finalized.get('unchanged') is not True:
                raise HereNowError('here.now finalize response changed the prepared version')
            after = self.site_details(slug)
            after_version = required_text(after, 'currentVersionId')
            if after_version != finalized_version:
                raise HereNowOutcomeUnknownError('finalized version differs on readback; reconcile')
            if manifest_hashes(after) != receipt.checksums:
                raise HereNowOutcomeUnknownError('finalized manifest differs; reconcile')
        except (URLError, OSError, HereNowError, ValueError) as exc:
            raise HereNowOutcomeUnknownError('finalize/readback outcome unknown; reconcile before retry') from exc
        return HereNowReceipt(slug, finalized_version, len(seen), False)

    def reconcile(self, slug: str, receipt: BuildReceipt) -> HereNowReceipt | None:
        verify_local_artifact(receipt)
        details = self.site_details(slug)
        if manifest_hashes(details) != receipt.checksums:
            return None
        return HereNowReceipt(slug, required_text(details, 'currentVersionId'), 0, True)
