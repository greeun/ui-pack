#!/usr/bin/env python3
"""Capture the screens before and after a pack is applied, and build one HTML file that compares them side by side.

Usage:
  # 1) Before: capture with the target app's dev server running (must be done before the install)
  python3 compare.py capture --base http://localhost:3000 --routes / /login --out <folder>/before
  # 2) After: restart the server, then capture the same routes
  python3 compare.py capture --base http://localhost:3000 --routes / /login --out <folder>/after
  # 3) Build the comparison page
  python3 compare.py page --before <folder>/before --after <folder>/after --out <folder>/index.html --title "App name"

Each route is captured three ways: wide (1440) light theme, wide dark theme, narrow (500) light theme.
The comparison page is one file with the images inside, so it opens directly in a browser. It offers "Side by side"
and "Overlay" (a slider moves the boundary).
capture also saves the app contract of each route (role and visible name of buttons, links, fields and headings,
placeholders, field names, link targets), and page writes the contract difference (removed, added) on the page and
to standard output. removed must be 0.
"""
import argparse, base64, html, json, pathlib, re, subprocess, sys, tempfile
from html.parser import HTMLParser

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
VARIANTS = [
    ("desktop-light", "Wide · light", 1440, 2000, 1),
    ("desktop-dark", "Wide · dark", 1440, 2000, 0),
    ("narrow-light", "Narrow · light", 500, 1600, 1),
]


# ---------------------------------------------------------------- App contract (visible names and roles)
VOID = {"input", "img", "br", "hr", "meta", "link", "source", "area", "base", "col", "embed", "track", "wbr"}
IMPLICIT = {"button": "button", "select": "combobox", "textarea": "textbox", "h1": "heading", "h2": "heading", "h3": "heading", "label": "label"}


class ContractParser(HTMLParser):
    """Collects the role and name of the elements a user sees and presses in the page DOM. This list must be the same before and after a pack is applied."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.items, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        at = dict(attrs)
        if tag in ("script", "style", "template", "svg"):
            self.skip += 1
            return
        if at.get("aria-hidden") == "true" or "hidden" in at:
            self.skip += 1 if tag not in VOID else 0
        if tag == "input":
            if self.skip:
                return
            typ = at.get("type", "text")
            if typ == "hidden":
                return
            role = at.get("role") or {"checkbox": "checkbox", "radio": "radio", "submit": "button", "button": "button", "search": "searchbox"}.get(typ, "textbox")
            name = at.get("aria-label") or at.get("value") if role == "button" else at.get("aria-label") or ""
            self.items.append(f"{role}: {name}".rstrip(": ") if name else role)
            if at.get("placeholder"):
                self.items.append(f"placeholder: {at['placeholder']}")
            if at.get("name"):
                self.items.append(f"field: {at['name']}")
            return
        if tag in VOID:
            return
        role = at.get("role") or (("link" if "href" in at else None) if tag == "a" else IMPLICIT.get(tag))
        self.stack.append({"tag": tag, "role": role, "label": at.get("aria-label"), "text": [], "own": [], "attrs": at, "hid": at.get("aria-hidden") == "true" or "hidden" in at})

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template", "svg"):
            self.skip = max(0, self.skip - 1)
            return
        if tag in VOID:
            return
        while self.stack:
            el = self.stack.pop()
            text = " ".join("".join(el["text"]).split())
            if self.stack:
                self.stack[-1]["text"].append(" " + text + " ")
            if el["hid"]:
                self.skip = max(0, self.skip - 1)
            own = " ".join("".join(el["own"]).split())
            if not el["role"] and own and len(own) <= 200 and not self.skip and not el["hid"]:
                self.items.append(f"text: {own}")  # text outside named elements (empty-state notes, descriptions ...)
            if el["role"] and not self.skip and not el["hid"]:
                name = el["label"] or text
                at = el["attrs"]
                item = f"{el['role']}: {name}" if name else el["role"]
                if el["role"] == "link" and at.get("href"):
                    item += f" → {at['href']}"
                self.items.append(item)
                if el["tag"] == "textarea":
                    if at.get("placeholder"):
                        self.items.append(f"placeholder: {at['placeholder']}")
                    if at.get("name"):
                        self.items.append(f"field: {at['name']}")
            if el["tag"] == tag:
                break

    def handle_data(self, data):
        if self.stack and not self.skip:
            self.stack[-1]["text"].append(data)
            self.stack[-1]["own"].append(data)


def contract(html_text: str) -> list[str]:
    p = ContractParser()
    p.feed(html_text)
    return sorted(set(p.items))


def slug(route: str) -> str:
    s = re.sub(r"[^0-9A-Za-z\uac00-\ud7a3]+", "-", route.strip("/")).strip("-")
    return s or "home"


def capture(a):
    if not pathlib.Path(CHROME).exists():
        sys.exit(f"Chrome not found: {CHROME}")
    out = pathlib.Path(a.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for route in a.routes:
        url = a.base.rstrip("/") + (route if route.startswith("/") else "/" + route)
        for key, _, w, h, scheme in VARIANTS:
            f = out / f"{slug(route)}__{key}.png"
            # Reduced motion must be on to capture the screen after its entrance motion ends. A fresh profile each time keeps a stored theme value from leaking in.
            with tempfile.TemporaryDirectory() as prof:
                subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-prefers-reduced-motion",
                                f"--user-data-dir={prof}", f"--blink-settings=preferredColorScheme={scheme}",
                                f"--virtual-time-budget={a.wait}", f"--window-size={w},{h}", f"--screenshot={f}", url],
                               capture_output=True, timeout=180)
            print(("captured " if f.exists() else "failed ") + f.name)
        with tempfile.TemporaryDirectory() as prof:
            dom = subprocess.run([CHROME, "--headless=new", f"--user-data-dir={prof}", "--force-prefers-reduced-motion",
                                  f"--virtual-time-budget={a.wait}", "--window-size=1440,2000", "--dump-dom", url],
                                 capture_output=True, text=True, timeout=180).stdout
        (out / f"{slug(route)}__contract.json").write_text(json.dumps(contract(dom), ensure_ascii=False, indent=1))
        manifest.append(route)
    (out / "routes.json").write_text(json.dumps(manifest, ensure_ascii=False))


def data_uri(f: pathlib.Path) -> str:
    # Converted to JPEG to keep the file small (sips on macOS). When the conversion fails the PNG goes in as it is.
    with tempfile.TemporaryDirectory() as d:
        jpg = pathlib.Path(d) / "x.jpg"
        r = subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82", str(f), "--out", str(jpg)], capture_output=True)
        if r.returncode == 0 and jpg.exists():
            return "data:image/jpeg;base64," + base64.b64encode(jpg.read_bytes()).decode()
    return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()


def page(a):
    before = pathlib.Path(a.before).expanduser().resolve()
    after = pathlib.Path(a.after).expanduser().resolve()
    routes = json.loads((before / "routes.json").read_text())
    sections, report = [], []
    for route in routes:
        rows = []
        cb, ca = before / f"{slug(route)}__contract.json", after / f"{slug(route)}__contract.json"
        if cb.exists() and ca.exists():
            b_items, a_items = set(json.loads(cb.read_text())), set(json.loads(ca.read_text()))
            gone, new_items = sorted(b_items - a_items), sorted(a_items - b_items)
            report.append((route, gone, new_items, len(b_items)))
            li = lambda xs: "".join(f"<li><code>{html.escape(x)}</code></li>" for x in xs) or "<li>none</li>"
            rows.append(f"""<div class="contract"><p><b>App contract</b> (roles and visible names, text, placeholders, field names, link targets): {len(b_items)} items before,
removed {len(gone)}, added {len(new_items)}</p>
<details{" open" if gone else ""}><summary>removed {len(gone)}</summary><ul>{li(gone)}</ul></details>
<details><summary>added {len(new_items)}</summary><ul>{li(new_items)}</ul></details></div>""")
        for key, label, w, _, _ in VARIANTS:
            b, f = before / f"{slug(route)}__{key}.png", after / f"{slug(route)}__{key}.png"
            if not (b.exists() and f.exists()):
                rows.append(f"<p class=miss>{html.escape(label)}: the {'before' if not b.exists() else 'after'} capture is missing.</p>")
                continue
            bu, fu = data_uri(b), data_uri(f)
            rows.append(f"""<figure class="pair" data-w="{w}">
<figcaption>{html.escape(label)}</figcaption>
<div class="side"><div><p>Before</p><img src="{bu}" alt="{html.escape(route)} before, {html.escape(label)}"></div><div><p>After</p><img src="{fu}" alt="{html.escape(route)} after, {html.escape(label)}"></div></div>
<div class="over" hidden><div class="stack"><img src="{bu}" alt=""><img class="top" src="{fu}" alt="{html.escape(route)} before and after overlay, {html.escape(label)}"></div>
<label>Boundary <input type="range" min="0" max="100" value="50"></label><p class="hint">Left is after, right is before.</p></div>
</figure>""")
        sections.append(f'<section><h2><code>{html.escape(route)}</code></h2>{"".join(rows)}</section>')
    title = html.escape(a.title or "Before and after the UI pack")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{color-scheme:light dark}}
body{{font-family:system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;margin:0 auto;max-width:1600px;padding:32px 24px 80px;line-height:1.5}}
h1{{font-size:26px;margin:0}} .lead{{opacity:.72;margin:4px 0 16px}}
.bar{{position:sticky;top:0;z-index:5;display:flex;gap:8px;padding:10px 0;background:Canvas;border-bottom:1px solid color-mix(in oklab,currentColor 15%,transparent)}}
.bar button{{font:inherit;padding:6px 14px;border-radius:999px;border:1px solid color-mix(in oklab,currentColor 40%,transparent);background:transparent;color:inherit;cursor:pointer}}
.bar button[aria-pressed=true]{{background:CanvasText;color:Canvas}}
section{{margin-top:40px}} h2{{font-size:20px}}
figure{{margin:16px 0 32px}} figcaption{{font-weight:600;margin-bottom:8px}}
.side{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .side p{{margin:0 0 4px;font-size:13px;opacity:.7}}
figure[data-w="500"] .side{{grid-template-columns:repeat(2,minmax(0,420px))}}
img{{width:100%;display:block;border:1px solid color-mix(in oklab,currentColor 15%,transparent);border-radius:6px}}
.stack{{position:relative;max-width:1100px}} .stack .top{{position:absolute;inset:0;clip-path:inset(0 50% 0 0)}}
figure[data-w="500"] .stack{{max-width:420px}}
.over label{{display:flex;gap:8px;align-items:center;margin-top:8px;max-width:600px}} .over input{{flex:1}}
.hint,.miss{{font-size:13px;opacity:.7}}
.contract{{padding:12px 16px;border:1px solid color-mix(in oklab,currentColor 20%,transparent);border-radius:8px;margin:8px 0 16px}} .contract p{{margin:0 0 6px}} .contract ul{{margin:4px 0 8px;font-size:13px}}
</style></head><body>
<h1>{title}</h1>
<p class="lead">The same routes captured under the same conditions (reduced motion, same window size). Only how the screen is drawn may change; what it does must stay the same.</p>
<div class="bar" role="group" aria-label="View mode"><button type="button" data-mode="side" aria-pressed="true">Side by side</button><button type="button" data-mode="over" aria-pressed="false">Overlay</button></div>
{"".join(sections)}
<script>
document.querySelectorAll('.bar button').forEach(b=>b.addEventListener('click',()=>{{
  const over=b.dataset.mode==='over';
  document.querySelectorAll('.bar button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
  document.querySelectorAll('.side').forEach(e=>e.hidden=over);
  document.querySelectorAll('.over').forEach(e=>e.hidden=!over);
}}));
document.querySelectorAll('.over input').forEach(r=>r.addEventListener('input',()=>{{
  r.closest('.over').querySelector('.top').style.clipPath=`inset(0 ${{100-r.value}}% 0 0)`;
}}));
</script>
</body></html>"""
    out = pathlib.Path(a.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    print(f"Comparison page: {out}  ({out.stat().st_size / 1024 / 1024:.1f}MB)")
    for route, gone, new_items, total in report:
        print(f"App contract {route}: {total} items before, removed {len(gone)}, added {len(new_items)}")
        for g in gone:
            print(f"  - removed: {g}")
        for n in new_items:
            print(f"  + added: {n}")


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
c = sub.add_parser("capture")
c.add_argument("--base", required=True)
c.add_argument("--routes", nargs="+", required=True)
c.add_argument("--out", required=True)
c.add_argument("--wait", type=int, default=8000, help="virtual time to wait for the screen to render (ms)")
p = sub.add_parser("page")
p.add_argument("--before", required=True)
p.add_argument("--after", required=True)
p.add_argument("--out", required=True)
p.add_argument("--title", default=None)
a = ap.parse_args()
capture(a) if a.cmd == "capture" else page(a)
