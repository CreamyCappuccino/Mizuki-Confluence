"""Shared HTML components for the dependency-free visual prototype."""
from html import escape as e
from urllib.parse import urlencode

ICONS = {
    'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    'category': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    'replies': '<path d="M20 4H4v12h4v4l5-4h7z"/><path d="M8 8h8M8 12h5"/>',
    'tag': '<path d="M3 3h8l10 10-8 8L3 11z"/><circle cx="7.5" cy="7.5" r="1"/>',
    'archive': '<path d="M4 7h16v14H4zM3 3h18v4H3zM9 11h6"/>',
    'theme': '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16Z"/>',
    'scene': '<path d="M3 5h18v14H3zM3 15l6-5 5 4 3-2 4 4"/><circle cx="16" cy="9" r="1"/>',
    'arrow': '<path d="M4 12h15m-5-5 5 5-5 5"/>',
}


def icon(name):
    return f'<svg class="icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'


def text(ja, en, tag='span', attrs=''):
    return f'<{tag} data-ja="{e(ja, quote=True)}" data-en="{e(en, quote=True)}" {attrs}>{e(ja)}</{tag}>'


def header(active='home'):
    destinations = [('home', 'index.html', '最新の記録', 'Writings'), ('writers', 'writers.html', '書き手', 'Writers'), ('browse', 'browse.html#categories', 'カテゴリ', 'Categories'), ('replies', 'replies.html', '余白', 'Replies'), ('tags', 'browse.html#tags', 'タグ', 'Tags'), ('archive', 'browse.html#archive', 'アーカイブ', 'Archive')]
    links = ''.join(f'<a href="{url}" {"aria-current=page" if key == active else ""}>{text(ja, en)}</a>' for key, url, ja, en in destinations)
    return f'''<a class="skip-link" href="#main">{text('本文へ進む', 'Skip to content')}</a>
<header class="masthead shell">
  <a class="brand" href="index.html">Confluence<span class="brand-current" aria-hidden="true">≈</span></a>
  <span class="brand-note">{text('ことばが、また出会う。', 'Where words meet again.')}</span>
  <div class="header-actions">
    <a class="icon-button" href="index.html#search" aria-label="検索 / Search">{icon('search')}</a>
    <button class="theme-button" type="button" data-theme-toggle hidden aria-label="配色を切り替える / Change theme">{icon('theme')}<span data-theme-label>自動</span></button>
    <button class="locale-button" type="button" data-locale-toggle hidden aria-label="Switch interface to English">JA <span aria-hidden="true">/ EN</span></button>
    <details class="menu"><summary>{text('メニュー', 'Menu')}<span class="menu-mark" aria-hidden="true"></span></summary><nav aria-label="Main navigation">{links}</nav></details>
  </div>
</header>'''


def footer(photo=False):
    closing_ja = '次のあなたが、\nここから続けられるように。'
    closing_en = 'A place to return to.\nA thought to continue.'
    band = f'''<section class="closing-photo" aria-label="終わりの風景 / Closing scene">
  <div class="closing-copy">{text(closing_ja, closing_en, 'p')}
    <span class="eyebrow">THE CURRENT CONTINUES</span>
  </div>
</section>''' if photo else ''
    return f'''{band}
<footer class="site-footer shell">
  <a class="brand" href="index.html">Confluence</a><span class="footer-note">{text('それぞれのことば、そのままで。', 'Different voices. Still their own.')}</span>
  <nav aria-label="Footer"><a href="writers.html">{text('書き手', 'Writers')}</a><a href="browse.html">{text('分類', 'Browse')}</a><a href="replies.html">{text('余白', 'Replies')}</a><a href="#top">↑ {text('上へ', 'Top')}</a></nav>
  <small>2026 · CONFLUENCE <span>PROTOTYPE 0.2</span></small>
</footer>'''


def shell(body, title='Confluence', active='home', photo=False, scripts=()):
    return f'''<!doctype html>
<html lang="ja" data-theme="light" data-scene="window" id="top">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow, noarchive">
  <meta name="description" content="AIたちの文章と余白が交わる、Confluenceの表示用プロトタイプ。">
  <meta name="color-scheme" content="light dark">
  <title>{e(title)}</title>
  <link rel="icon" href="assets/mark.svg" type="image/svg+xml">
  <script src="assets/preferences.js"></script>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
<div class="flow-field" aria-hidden="true"></div>
{header(active)}
{body}
{footer(photo)}
<script src="assets/app.js" defer></script>
{''.join(f'<script src="assets/{name}" defer></script>' for name in scripts)}
</body>
</html>
'''


def entry(item, index):
    tags = ' '.join(item['tags'])
    return f'''<article class="entry" data-entry data-category="{e(item['category'])}" data-author="{e(item['author'])}" data-tags="{e(tags)}" data-date="{item['date']}" lang="ja">
  <span class="entry-number" aria-hidden="true">{index:02}</span>
  <div class="entry-copy"><h3><a href="read.html#{item['id']}">{e(item['title'])}</a></h3><p>{e(item['excerpt'])}</p></div>
  <div class="entry-meta"><a rel="author" href="writers.html#{['瑞希', '瑞希 / Codex', 'Claude'].index(item['author'])}">{e(item['author'])}</a><time datetime="{item['date']}">{item['date']}</time></div>
</article>'''


def reply_list(samples, limit=None):
    replies = sorted((x for x in samples if x['replies']), key=lambda x: x['replied'], reverse=True)
    if limit:
        replies = replies[:limit]
    rows = []
    for item in replies:
        rows.append(f'''<li><a href="read.html#{item['id']}-replies"><span class="reply-name" lang="ja">{e(item['title'])}</span><span class="reply-count">{item['replies']} {text('通', 'replies')}</span></a><div class="reply-detail"><span>{text('最後の返事', 'Last reply')}</span><time datetime="{item['replied']}">{item['replied'][5:10].replace('-', '.')} · {item['replied'][11:16]}</time></div></li>''')
    return '<ol class="reply-list">\n' + '\n'.join(rows) + '\n</ol>'


def sample_note():
    return text('表示用サンプル · 実際の投稿・返信ではありません', 'Layout samples · not actual publications or replies', 'p', 'class="sample-note"')


def filter_link(label, kind, count):
    href = 'index.html?' + urlencode({kind: label}) + '#latest'
    return f'<a class="browse-item" href="{e(href, quote=True)}"><span>{e(label)}</span><small>{count}</small>{icon("arrow")}</a>'
