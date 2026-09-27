"""Optional Chromium interaction smoke; no CSS/visual or external-host claim."""
from dataclasses import replace
from pathlib import Path
import sys
import os
import shutil
from uuid import UUID

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from confluence_release.artifacts import SEARCH_JS
from confluence_release.site_renderer import render_pages
from phase2_support import CONFIG,article


def main():
    from playwright.sync_api import sync_playwright
    rows=tuple(replace(article(f'ART{99990001+i}'), manuscript_id=UUID(int=i+1),
                       revision_id=UUID(int=i+100)) for i in range(10))
    html=render_pages(rows,CONFIG)['index.html'].decode()
    with sync_playwright() as p:
        executable=os.environ.get('CONFLUENCE_CHROMIUM_EXECUTABLE') or shutil.which('chromium')
        options={'executable_path':executable} if executable else {}
        browser=p.chromium.launch(**options, args=['--no-sandbox'] if sys.platform=='linux' else [])
        page=browser.new_page()
        # No file/localhost navigation; render the exact generated HTML in memory.
        page.route('**/*',lambda route:route.abort())
        page.set_content(html)
        page.add_script_tag(content=SEARCH_JS)
        page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
        assert page.locator('[data-release-entry]:not([hidden])').count()==6
        page.locator('#release-more').click()
        assert page.locator('[data-release-entry]:not([hidden])').count()==10
        page.locator('#release-search').fill('該当なし synthetic-no-match')
        assert page.locator('[data-release-entry]:not([hidden])').count()==0
        page.locator('#release-search').fill('合成')
        assert page.locator('[data-release-entry]:not([hidden])').count()==6
        assert page.locator('#release-count').text_content()=='6 / 10'
        browser.close()
    print('PASS: Chromium search / in-place expansion / no-results / reset; interaction only')


if __name__=='__main__':main()
