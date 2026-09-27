"""AIL ReleaseBuilder/checksum pattern: immutable whole-site artifacts."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from confluence_pressroom.release_checksums import (
    MANIFEST, safe_relative_path, verify_local_artifact as verify_safety_artifact,
)

from .config import ReleaseConfig, json_bytes
from .projection import ProjectionArticle, projection_digest
from .site_renderer import render_pages


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(value: str) -> str:
    return safe_relative_path(value)


def read_files(root: Path) -> dict[str, bytes]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError('artifact directory is missing or not ordinary')
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('artifact symlinks are not supported')
        if path.is_file():
            result[safe_relative(path.relative_to(root).as_posix())] = path.read_bytes()
    return result


@dataclass(frozen=True)
class BuildReceipt:
    output: Path
    content_digest: str
    checksums: dict[str, str]
    article_routes: tuple[str, ...]

    def as_record(self) -> dict[str, object]:
        # Private JOB receipt, never shipped in the artifact.
        return dict(output=str(self.output), content_digest=self.content_digest,
                    checksums=dict(self.checksums), article_routes=list(self.article_routes))

    @classmethod
    def from_record(cls, record):
        return cls(Path(record['output']), record['content_digest'],
                   dict(record['checksums']), tuple(record['article_routes']))


def verify_local_artifact(receipt: BuildReceipt) -> None:
    # The pin is from the private JOB receipt, never recomputed from the artifact.
    verify_safety_artifact(receipt.output,
                           expected_manifest_sha256=receipt.checksums.get(MANIFEST))
    actual = {p: sha256(v) for p, v in read_files(receipt.output).items()}
    # Include inventory: appended files / routes cannot be silently uploaded.
    if actual != receipt.checksums:
        raise ValueError('local artifact bytes or inventory differ from the frozen release')


SEARCH_JS = '''document.addEventListener('DOMContentLoaded',()=>{
const q=document.getElementById('release-search');if(!q)return;
const rows=[...document.querySelectorAll('[data-release-entry]')];
const more=document.getElementById('release-more'),count=document.getElementById('release-count');
const params=new URLSearchParams(location.search);let shown=6;q.value=params.get('q')||'';
const parse=v=>{try{return JSON.parse(v||'[]');}catch{return [];}};
const active=['category','tag','author','month'].some(k=>params.has(k));
const banner=document.getElementById('release-filter');if(banner)banner.hidden=!active;
function update(){const term=q.value.toLocaleLowerCase();let matched=0;
for(const row of rows){const cats=parse(row.dataset.categories),tags=parse(row.dataset.tags),authors=parse(row.dataset.authors);
const ok=(row.textContent+' '+tags.join(' ')+' '+cats.flat().join(' ')).toLocaleLowerCase().includes(term)
&&(!params.has('tag')||tags.includes(params.get('tag')))
&&(!params.has('author')||authors.includes(params.get('author')))
&&(!params.has('month')||row.dataset.month===params.get('month'))
&&(!params.has('category')||cats.some(v=>JSON.stringify(v)===JSON.stringify(parse(params.get('category')))));
row.hidden=!ok||(++matched>shown&&ok);}
if(more)more.hidden=matched<=shown;if(count)count.textContent=Math.min(shown,matched)+' / '+matched;
}
q.form?.addEventListener('submit',e=>{e.preventDefault();shown=6;update();});
q.addEventListener('input',()=>{shown=6;update();});more?.addEventListener('click',()=>{shown+=6;update();});update();
});'''



class ReleaseBuilder:
    """Adapted from AIL public_site/release.py; v0.2 assets, Confluence pages."""
    def __init__(self, *, source_assets: Path, config: ReleaseConfig, source_commit: str):
        self.source_assets = source_assets
        self.config = config
        self.source_commit = source_commit

    def build(self, articles: tuple[ProjectionArticle, ...], output: Path) -> BuildReceipt:
        if not output.is_absolute() or output.exists():
            raise ValueError('release output must be new and absolute')
        content_digest = projection_digest(articles)
        files = render_pages(articles, self.config)
        routes = tuple(sorted(p for p in files if '/articles/' in p))
        if not self.source_assets.is_dir():
            raise ValueError('Confluence v0.2 assets not found')
        for name, data in read_files(self.source_assets).items():
            if Path(name).suffix.lower() in {'.css', '.js', '.svg', '.webp', '.png', '.jpg', '.woff2'}:
                files['assets/' + name] = data
        files['assets/release-search.js'] = SEARCH_JS.encode()
        files['release-manifest.json'] = json_bytes(dict(
            format='confluence-static-release/v1', source_commit=self.source_commit,
            content_digest=content_digest, article_count=len(articles),
            article_routes=routes, external_discovery='discouraged', sitemap=False)) + b'\n'
        # AIL checksum file is public; stronger expected inventory is in the JOB.
        sums = {p: sha256(data) for p, data in sorted(files.items())}
        files['checksums.sha256'] = ''.join(f'{v}  {p}\n' for p, v in sums.items()).encode()
        sums['checksums.sha256'] = sha256(files['checksums.sha256'])
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f'.{output.name}-', dir=output.parent))
        try:
            for name, data in files.items():
                dest = tmp / safe_relative(name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            tmp.rename(output)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        receipt = BuildReceipt(output, content_digest, sums, routes)
        verify_local_artifact(receipt)
        return receipt
