"""Synthetic independent nine-meta fixture; NOT saved production byte evidence."""
from dataclasses import replace

from confluence_pressroom.here_now_image_html import HereNowImageHtmlPolicy
from phase2_support import CONFIG

# Name order also independently confirmed from saved evidence in CX-MSG0337.
ORDER = ('og:title', 'og:description', 'og:url', 'og:type', 'og:image',
         'og:image:width', 'og:image:height', 'twitter:image', 'twitter:card')
IMAGE = 'https://here.now/og/synthetic-confluence.jpg'
SOURCE = b'<!doctype html><html><head><title>Original</title></head><body>unchanged</body></html>'


def image_policy(**changes):
    profile = HereNowImageHtmlPolicy(here_now_base=CONFIG.here_now_base,
        nor_base=CONFIG.nor_base, title='Confluence', description='Synthetic description.',
        expected_manifest_sha256='a' * 64, image_url=IMAGE,
        image_width=1280, image_height=720)
    return replace(profile, **changes)


def literal_image_block(base, relative='index.html'):
    # Independent literal, not policy.predict() or its field mapping.
    return (f'<meta property="og:title" content="Confluence" />\n'
        '<meta property="og:description" content="Synthetic description." />\n'
        f'<meta property="og:url" content="{base}/{relative}" />\n'
        '<meta property="og:type" content="website" />\n'
        '<meta property="og:image" content="https://here.now/og/synthetic-confluence.jpg" />\n'
        '<meta property="og:image:width" content="1280" />\n'
        '<meta property="og:image:height" content="720" />\n'
        '<meta name="twitter:image" content="https://here.now/og/synthetic-confluence.jpg" />\n'
        '<meta name="twitter:card" content="summary_large_image" />').encode()
