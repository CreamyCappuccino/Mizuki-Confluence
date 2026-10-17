"""Synthetic pre-metadata artifacts, frozen before legacy recovery tests run.

This fixture creates old-style HTML at build time. It never normalizes a remote
response or changes a receipt after freezing. Production has no legacy renderer
switch: newly built artifacts always receive renderer-owned metadata.
"""
from html import escape
from unittest.mock import patch

from confluence_release.artifacts import ReleaseBuilder
from confluence_release.config import ROBOTS


def legacy_shell(body, title, *, lang='ja', **unused):
    return (f'<!doctype html><html lang="{escape(lang, quote=True)}"><head>'
            f'<meta name="robots" content="{ROBOTS}">'
            f'<title>{escape(title)}</title></head><body>{body}</body></html>')


class LegacyReleaseBuilder(ReleaseBuilder):
    def build(self, articles, output):
        with patch('confluence_release.site_renderer.shell', legacy_shell):
            return super().build(articles, output)
