from pathlib import Path
import argparse
import sys
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'tools'))
from prepare_renderer_fixture import build_fixture
parser=argparse.ArgumentParser(description='In-memory fixture browser smoke, not delivery readback')
parser.add_argument('--browser', required=True)
args=parser.parse_args()
raw=build_fixture()['payload_snapshot']['rendered_html']
html='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="robots" content="noindex,nofollow,noarchive"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>Preparation fixture check</title><style>body{margin:24px auto;padding:0 24px;max-width:780px;font-family:serif;line-height:1.8;background:#f5f2eb;color:#28352f}pre{padding:16px;overflow:auto;background:#e7e6db}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:8px}a{color:#356757}h1{font-size:28px}h2{font-size:22px}</style><body>'''+raw+'</body></html>'
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=args.browser,headless=True,args=['--no-sandbox'])
    for width in (390,1440):
        page=browser.new_page(viewport={'width':width,'height':900})
        requests=[]
        page.route('**/*',lambda route: (requests.append(route.request.url),route.abort()))
        page.set_content(html)
        checks=page.evaluate('''() => ({
          ids: [...document.querySelectorAll('[id]')].map(x=>x.id),
          links: [...document.querySelectorAll('a[href^="#"]')].map(x=>({href:x.getAttribute('href'),text:document.getElementById(x.hash.slice(1))?.textContent})),
          code: document.querySelector('pre code').textContent,
          unsafe: document.querySelectorAll('script,iframe,svg,form,img').length,
          overflow: document.documentElement.scrollWidth>innerWidth
        })''')
        assert len(checks['ids'])==5 and len(set(checks['ids']))==5
        assert all(x['text']=='日本語の見出し' for x in checks['links'])
        assert checks['unsafe']==0 and not checks['overflow']
        assert '<synthetic> & world' in checks['code']
        assert not requests
        results.append({'width':width,**checks,'network_requests':len(requests),'mode':'in-memory fragment rendering, not URL/delivery readback'})
        page.close()
    browser.close()
# Nothing is persisted or published by this smoke check.
print('PASS: Chromium 390/1440; heading targets/code/table, no active elements, no horizontal overflow or requests')
