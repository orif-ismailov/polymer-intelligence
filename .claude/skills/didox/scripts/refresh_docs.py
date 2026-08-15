"""Re-pull `reference/*.md` from the live Didox docs.

    uv run --no-project --with html2text python scripts/refresh_docs.py
    uv run --no-project --with html2text python scripts/refresh_docs.py --check

Didox ships API changes with no changelog (the only signal is t.me/didoxapiupdates),
so the mirror drifts. This regenerates it.

Why it is not just a WebFetch: api-docs.didox.uz is a **Wiki.js** SPA, so a plain
fetch returns the shell and a summarizer sees nothing. Two facts make it scrapeable:

  * `POST /graphql {pages{list(locale:"ru"){id path title}}}` is PUBLIC and returns
    the whole page index. (`pages.single`, which would hand over raw markdown, is
    NOT — it 403s with "You are not authorized to view this page".)
  * the rendered content IS server-rendered into the HTML, inside
    `<template slot="contents">…</template>` on the `<page>` element.

So: GraphQL for discovery, HTML for content, html2text + fixups for markdown.
`--check` reports drift (new/removed pages, changed `updatedAt`) without writing.
"""

from __future__ import annotations

import argparse
import html as htmlmod
import json
import re
import sys
import urllib.request
from pathlib import Path

import html2text

BASE = "https://api-docs.didox.uz"
REFERENCE = Path(__file__).resolve().parent.parent / "reference"
UA = "Mozilla/5.0 (compatible; didox-skill-mirror)"

# Stable slug per doc path, so file names (and links into them) don't churn.
SLUGS: dict[str, str] = {
    "integrators-eimzo": "01-eimzo",
    "integrators-registration": "02-registration",
    "home": "03-login",
    "integrators-account": "04-account",
    "integrators-profile": "05-profile",
    "integrators-documents": "06-documents",
    "integrators-property-documents": "07-document-json",
    "integrators-utils": "08-utils",
    "integrators-catalogs": "09-catalogs",
    "integrators-document-template": "10-document-templates",
    "integrators-newoffersign": "11-offer-signing",
}


def _get(url: str, *, data: bytes | None = None) -> str:
    headers = {"User-Agent": UA}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310 — fixed host
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def list_pages(locale: str = "ru") -> list[dict]:
    """The public GraphQL page index."""
    query = json.dumps({"query": f'{{pages{{list(locale:"{locale}"){{id path title}}}}}}'})
    payload = json.loads(_get(f"{BASE}/graphql", data=query.encode()))
    if "errors" in payload and not payload.get("data"):
        raise RuntimeError(f"graphql failed: {payload['errors']}")
    return payload["data"]["pages"]["list"]


def _page_attrs(html: str) -> dict[str, str]:
    m = re.search(r"<page\b(.*?)>", html, re.S)
    return dict(re.findall(r'([a-z:@-]+)="(.*?)"', m.group(1), re.S)) if m else {}


def _contents(html: str) -> str:
    m = re.search(r'<template slot="contents">(.*?)</template>\s*</page>', html, re.S)
    if not m:
        m = re.search(r'<template slot="contents">(.*)</page>', html, re.S)
    return m.group(1) if m else ""


def _to_markdown(frag: str) -> str:
    # Wiki.js emits <pre class="prismjs line-numbers"><code class="language-X">.
    # Stash the language so html2text's [code] markers can become real fences.
    def code(m: re.Match) -> str:
        lang = (m.group("lang") or "").strip()
        return f"<pre><code>@@LANG:{lang}@@\n{m.group('body')}</code></pre>"

    frag = re.sub(
        r'<pre[^>]*>\s*<code(?:\s+class="language-(?P<lang>[^"]*)")?[^>]*>'
        r"(?P<body>.*?)</code>\s*</pre>",
        code, frag, flags=re.S,
    )
    frag = re.sub(r'<a href="#[^"]*" class="toc-anchor">.*?</a>', "", frag, flags=re.S)

    conv = html2text.HTML2Text()
    conv.body_width = 0
    conv.mark_code = True
    conv.escape_snob = False
    conv.protect_links = True
    md = conv.handle(frag)

    def fence(m: re.Match) -> str:
        body = m.group(1)
        lm = re.match(r"\s*@@LANG:([a-z0-9]*)@@\n?", body)
        lang = ""
        if lm:
            lang, body = lm.group(1), body[lm.end():]
        body = "\n".join(ln[4:] if ln.startswith("    ") else ln for ln in body.split("\n"))
        return "```" + lang + "\n" + body.strip("\n") + "\n```"

    md = re.sub(r"\[code\]\n?(.*?)\[/code\]", fence, md, flags=re.S)
    md = re.sub(r"@@LANG:[a-z0-9]*@@\n?", "", md)
    return re.sub(r"\n{4,}", "\n\n\n", md).strip() + "\n"


def _cleanup(md: str) -> str:
    """Post-conversion fixups. Never touch fenced code except to unwrap it."""
    parts = re.split(r"(```.*?```)", md, flags=re.S)
    for i, part in enumerate(parts):
        if part.startswith("```"):
            # blockquote markers leak into code blocks nested in a Wiki.js callout
            lines = part.split("\n")
            body = lines[1:-1]
            if any(re.match(r"^\s*>", ln) for ln in body):
                cleaned = []
                for ln in body:
                    while ">" in ln and re.match(r"^\s*>\s{0,5}", ln):
                        ln = re.sub(r"^\s*>\s{0,5}", "", ln, count=1)
                    cleaned.append(ln)
                while cleaned and not cleaned[0].strip():
                    cleaned.pop(0)
                while cleaned and not cleaned[-1].strip():
                    cleaned.pop()
                parts[i] = "\n".join([lines[0], *cleaned, lines[-1]])
            continue
        part = re.sub(r"(\d)\\\.", r"\1.", part)                            # 1\. → 1.
        part = re.sub(r"\(</ru/", f"({BASE}/ru/", part)                     # relative → absolute
        part = re.sub(rf"(\({re.escape(BASE)}/ru/[^)\s]*?)>\)", r"\1)", part)
        part = re.sub(r"^(#+)\s+", r"\1 ", part, flags=re.M)                # "#  X" → "# X"
        part = re.sub(r"^# \|", r"\\# |", part, flags=re.M)                 # a "#"-headed table
        parts[i] = part
    return "".join(parts)


def fetch_page(path: str) -> tuple[str, str, str]:
    """Return (title, updated_at, markdown) for one doc path."""
    html = _get(f"{BASE}/ru/{path}")
    attrs = _page_attrs(html)
    frag = _contents(html)
    if not frag:
        raise RuntimeError(f"no <template slot='contents'> in /ru/{path} — the wiki theme changed")
    title = htmlmod.unescape(attrs.get("title", path))
    header = (
        f"# {title}\n\n"
        f"> Verbatim mirror of <{BASE}/ru/{path}>\n"
        f"> Source last updated: {attrs.get('updated-at', '')}\n\n---\n\n"
    )
    return title, attrs.get("updated-at", ""), header + _cleanup(_to_markdown(frag))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = ap.parse_args(argv)

    pages = list_pages()
    known = {p["path"] for p in pages}

    if new := known - SLUGS.keys():
        print(f"!! NEW PAGES published since this skill was written: {sorted(new)}\n"
              f"   add them to SLUGS in {Path(__file__).name} and to the SKILL.md reference map",
              file=sys.stderr)
    if gone := SLUGS.keys() - known:
        print(f"!! pages no longer published: {sorted(gone)}", file=sys.stderr)

    changed = 0
    for page in sorted(pages, key=lambda p: p["title"]):
        slug = SLUGS.get(page["path"])
        if not slug:
            continue
        title, updated, md = fetch_page(page["path"])
        target = REFERENCE / f"{slug}.md"
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        if old == md:
            print(f"  = {slug:24} {title}")
            continue
        changed += 1
        was = re.search(r"^> Source last updated: (.*)$", old, re.M)
        stamp = f"{was.group(1)[:10] if was else '—'} → {updated[:10]}"
        if args.check:
            print(f"  ~ {slug:24} {title}   ({stamp})")
        else:
            target.write_text(md, encoding="utf-8")
            print(f"  ✎ {slug:24} {title}   ({stamp})")

    if args.check and changed:
        print(f"\n{changed} page(s) drifted — re-run without --check to update the mirror")
        return 1
    print(f"\n{'drift in' if args.check else 'updated'} {changed} page(s); {len(SLUGS)} mirrored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
