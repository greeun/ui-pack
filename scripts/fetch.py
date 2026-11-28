#!/usr/bin/env python3
"""Fetch a published UI pack (a git repository such as github.com/<owner>/ui-pack-<pack>) into the pack store.

Usage:
  python3 fetch.py <repository URL> [--home <pack store>]

The pack store is $UI_PACK_HOME (default ~/.axt/vault/ui-pack); the pack lands in <pack store>/packs/<name from pack.json>.
A fetched pack is someone else's code, so before it is moved into the pack store it is checked:
  - pack.json exists and names the pack with lowercase letters, digits and "-", and that pack does not exist yet
  - no symlinks in the repository
  - every "from" of the install list stays inside the pack and every "to" stays inside the target project
Prints the npm packages the pack will install, for the user to review before applying.
Exit code 3: refused (the checks above); nothing is left in the pack store.
"""
import argparse, json, os, pathlib, re, shutil, subprocess, sys, tempfile
from typing import NoReturn

ap = argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("--home", default=os.environ.get("UI_PACK_HOME") or "~/.axt/vault/ui-pack")
a = ap.parse_args()

url = a.url.strip().removesuffix("/")
if not re.fullmatch(r"https://[\w.-]+/[\w.-]+/[\w.-]+(\.git)?|file://\S+|/\S+", url):
    sys.exit("Give the https address of the pack repository, e.g. https://github.com/<owner>/ui-pack-<pack>")
packs = pathlib.Path(a.home).expanduser() / "packs"
packs.mkdir(parents=True, exist_ok=True)


def refuse(msg) -> NoReturn:
    print(f"Not fetched: {msg}", file=sys.stderr)
    sys.exit(3)


def check(root: pathlib.Path) -> dict:
    links = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_symlink()]
    if links:
        refuse(f"the repository contains symlinks: {', '.join(links[:5])}")
    try:
        meta = json.loads((root / "pack.json").read_text())
    except (OSError, ValueError):
        refuse("no readable pack.json at the top of the repository (is this a UI pack?)")
    name = meta.get("name") if isinstance(meta, dict) else None
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
        refuse(f"pack.json has no valid name: {name!r}")
    entries = meta.get("install")
    if not isinstance(entries, list) or not entries:
        refuse("pack.json has no install list")
    for e in entries:
        src, dst = (e.get("from"), e.get("to")) if isinstance(e, dict) else (None, None)
        if not isinstance(src, str) or not isinstance(dst, str):
            refuse(f"install entry without from/to: {e!r}")
        if not (root / src).resolve().is_relative_to(root.resolve()):
            refuse(f"install entry reads outside the pack: {src}")
        parts = pathlib.PurePosixPath(dst.replace("{src}", "src")).parts
        if dst.startswith("/") or ".." in parts:
            refuse(f"install entry writes outside the target project: {dst}")
    return meta


with tempfile.TemporaryDirectory(dir=packs, prefix=".fetch-") as tmp:
    clone = pathlib.Path(tmp) / "pack"
    r = subprocess.run(["git", "clone", "--depth", "1", "--no-local", "--quiet", url, str(clone)], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"git clone failed: {r.stderr.strip()}")
    meta = check(clone)
    dest = packs / meta["name"]
    if dest.exists():
        refuse(f"a pack named {meta['name']} already exists: {dest} (remove or rename it first)")
    shutil.move(str(clone), dest)

deps = {**meta.get("dependencies", {}), **meta.get("devDependencies", {})}
print(f"Fetched {meta['name']} {meta.get('version', '')} into {dest}")
print(f"  {meta.get('description', '')}")
print(f"  requires: {json.dumps(meta.get('requires', {}), ensure_ascii=False)}")
print(f"  npm packages it installs: {', '.join(f'{k}@{v}' for k, v in deps.items()) or 'none'}")
print("This pack is someone else's code: review its files and the npm packages above before applying it.")
print(f"Pack viewer (optional, builds with Next.js): python3 {pathlib.Path(__file__).resolve().parent / 'build-view.py'} {dest}")
