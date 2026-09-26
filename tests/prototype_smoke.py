"""Offline Chromium UI checks. Installs nothing and never contacts the network.

Needs Playwright for Python and Chromium. Run:
  python tests/prototype_smoke.py --browser /usr/bin/chromium
Optional screenshots: --screenshots /tmp/confluence-review
The HTML, JS, CSS, and local images are inlined only in this test harness.
"""
from pathlib import Path
from base64 import b64encode
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import argparse
import re

ROOT = Path(__file__).resolve().parents[1] / 'prototype'


def inlined(name='index.html'):
    html = (ROOT / name).read_text(encoding='utf-8')
    css = '\n'.join((ROOT / 'assets' / file).read_text(encoding='utf-8') for file in ('tokens.css', 'layout.css', 'reading.css', 'motion.css'))
    def image(match):
        file = ROOT / 'assets' / match.group(1)
        mime = 'image/svg+xml' if file.suffix == '.svg' else 'image/webp'
        return 'url("data:' + mime + ';base64,' + b64encode(file.read_bytes()).decode() + '")'
    css = re.sub(r"url\(['\"]?\./([^)'\"]+)['\"]?\)", image, css)
    html = html.replace('<link rel="stylesheet" href="assets/styles.css">', f'<style>{css}</style>')
    html = re.sub(r'<link rel="icon"[^>]+>', '', html)
    return re.sub(r'<script src="assets/([^"]+)"[^>]*></script>', lambda match: '<script>' + (ROOT / 'assets' / match.group(1)).read_text(encoding='utf-8') + '</script>', html)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()
    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if 'id' in attrs:
            assert attrs['id'] not in self.ids, f'duplicate ID {attrs["id"]}'
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])


def static_links():
    documents = {}
    for path in ROOT.glob('*.html'):
        parser = LinkParser()
        parser.feed(path.read_text(encoding='utf-8'))
        documents[path.name] = parser
    checked = 0
    for name, parser in documents.items():
        for href in parser.links:
            url = urlsplit(href)
            assert not url.scheme, f'unexpected external link {href}'
            target = unquote(url.path) or name
            assert target in documents, f'missing local page {target}'
            if url.fragment:
                assert unquote(url.fragment) in documents[target].ids, f'missing anchor {href}'
            checked += 1
    return checked


def main():
    from playwright.sync_api import sync_playwright
    args = argparse.ArgumentParser()
    args.add_argument('--browser', default='/usr/bin/chromium')
    args.add_argument('--screenshots', type=Path)
    config = args.parse_args()
    if config.screenshots:
        config.screenshots.mkdir(parents=True, exist_ok=True)
    print(f'PASS local links: {static_links()}')
    cases = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=config.browser, headless=True, args=['--no-sandbox'])
        for width, height in [(320, 740), (390, 844), (820, 960), (1024, 800), (1440, 960), (1920, 1080)]:
            for dark in (False, True):
                page = browser.new_page(viewport={'width': width, 'height': height}, color_scheme='dark' if dark else 'light')
                errors, network = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: network.append(request.url))
                page.set_content(inlined(), wait_until='load')
                page.wait_for_timeout(100)
                assert not errors, errors
                assert not network, network
                assert page.locator('[data-entry]:visible').count() == 6
                assert page.locator('#recent-replies li').count() == 5
                dimensions = page.evaluate('({overflow:document.documentElement.scrollWidth>innerWidth, first:document.querySelector(".entry:not([hidden])").getBoundingClientRect().top})')
                assert not dimensions['overflow'], (width, dark, dimensions)
                assert dimensions['first'] < height - 70, (width, dark, dimensions)
                page.locator('[data-locale-toggle]').click()
                assert page.locator('#latest-title').inner_text() == 'Recent writings'
                assert page.locator('[data-entry]').first.get_attribute('lang') == 'ja'
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.locator('[data-locale-toggle]').click()
                if config.screenshots and width in (390, 820, 1440):
                    page.screenshot(path=str(config.screenshots / f'{width}-{ "night" if dark else "day" }.png'), full_page=True)
                page.locator('[data-load-more]').click()
                assert page.locator('[data-entry]:visible').count() == 10
                assert not page.locator('[data-load-more]').is_visible()
                page.evaluate('document.getElementById("search").open=true')
                page.locator('#query').fill('Claude')
                assert page.locator('[data-entry]:visible').count() == 3
                page.locator('#query').fill('NO_MATCH_732891')
                assert page.locator('[data-entry]:visible').count() == 0
                assert page.locator('[data-empty]').is_visible()
                page.locator('#query').fill('')
                assert page.locator('[data-entry]:visible').count() == 10
                page.locator('[data-scene-toggle]').click()
                assert page.locator('html').get_attribute('data-scene') == 'afternoon'
                page.locator('[data-theme-toggle]').click()
                assert page.locator('html').get_attribute('data-theme') == 'light'
                page.locator('[data-theme-toggle]').click()
                assert page.locator('html').get_attribute('data-theme') == 'dark'
                page.locator('.menu summary').click()
                assert page.locator('.menu nav').is_visible()
                page.keyboard.press('Escape')
                assert not page.locator('.menu nav').is_visible()
                assert not errors, errors
                page.close()
                cases += 1
        page = browser.new_page(reduced_motion='reduce', viewport={'width': 390, 'height': 844})
        page.set_content(inlined(), wait_until='load')
        assert page.locator('.entry').first.evaluate('(node)=>getComputedStyle(node).opacity') == '1'
        assert page.locator('.flow-field').evaluate('(node)=>getComputedStyle(node).animationName') == 'none'
        page.locator('[data-entry] h3 a').first.evaluate('(node)=>node.textContent="非常に長い題名".repeat(20)')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.close()
        page = browser.new_page(java_script_enabled=False)
        page.set_content(inlined(), wait_until='load')
        assert page.locator('[data-entry]:visible').count() == 10
        page.close()
        for name in ('writers.html', 'browse.html', 'replies.html', 'read.html'):
            page = browser.new_page(viewport={'width': 390, 'height': 844})
            errors=[]
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.set_content(inlined(name), wait_until='load')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), name
            assert not errors, (name, errors)
            if name == 'read.html':
                page.evaluate('location.hash="unfinished-replies"')
                page.wait_for_timeout(60)
                assert page.locator('[data-reading]:visible').count() == 1
                assert page.locator('#unfinished-replies .response').count() == 2
            page.close()
        browser.close()
    print(f'PASS {cases} viewport/theme cases; JA/EN, load-more, search/empty, scene/theme controls, menu, long title, reduced motion, no-JS, four secondary pages, reply fragment')
    print('Boundary: in-memory Chromium rendering; HTTP/file navigation and native Mac/Safari not exercised here.')


if __name__ == '__main__':
    main()
