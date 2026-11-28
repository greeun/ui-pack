#!/usr/bin/env python3
"""Self-check for fetch.py and the outside-the-pack guard of install.py, with local git repositories. Run: python3 scripts/test_fetch.py"""
import json, os, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
tmp = pathlib.Path(tempfile.mkdtemp(prefix="ui-pack-fetch-test-"))
home = tmp / "home"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "init.defaultBranch=main"]


def repo(name, pack_json, files=None, link=None):
    d = tmp / "repos" / name
    (d / "tokens").mkdir(parents=True)
    (d / "tokens" / "globals.css").write_text(":root{}\n")
    (d / "pack.json").write_text(json.dumps(pack_json))
    for rel, text in (files or {}).items():
        (d / rel).write_text(text)
    if link:
        os.symlink(link, d / "leak.txt")
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
        subprocess.run(GIT + cmd, cwd=d, check=True)
    return str(d)


def fetch(url):
    return subprocess.run([sys.executable, str(HERE / "fetch.py"), url, "--home", str(home)], capture_output=True, text=True)


good = {"name": "calmgrid", "version": "1.0.0", "requires": {}, "dependencies": {"clsx": "^2"},
        "install": [{"from": "tokens/globals.css", "to": "{src}/app/globals.css", "mode": "copy"}]}

r = fetch(repo("ok", good))
assert r.returncode == 0, r.stderr
assert (home / "packs" / "calmgrid" / "pack.json").is_file()
assert "clsx@^2" in r.stdout, r.stdout  # the npm packages are shown for review
assert not [p for p in (home / "packs").iterdir() if p.name.startswith(".fetch-")]  # no temporary folder left

cases = {
    "exists": (good, None, "already exists"),
    "escape-from": ({**good, "name": "a", "install": [{"from": "../../secret", "to": "x", "mode": "copy"}]}, None, "reads outside the pack"),
    "escape-to": ({**good, "name": "b", "install": [{"from": "tokens/globals.css", "to": "{src}/../../x", "mode": "copy"}]}, None, "writes outside"),
    "bad-name": ({**good, "name": "../x"}, None, "no valid name"),
    "symlink": ({**good, "name": "c"}, "/etc/hosts", "symlinks"),
}
for key, (meta, link, msg) in cases.items():
    r = fetch(repo(key, meta, link=link))
    assert r.returncode == 3 and msg in r.stderr, (key, r.returncode, r.stderr)
    assert not (home / "packs" / meta["name"]).exists() or key == "exists", key
assert sorted(p.name for p in (home / "packs").iterdir()) == ["calmgrid"]

# install.py refuses a pack file outside the pack even when the pack was not fetched with fetch.py
bad = home / "packs" / "local-bad"
(bad / "tokens").mkdir(parents=True)
(tmp / "secret.txt").write_text("secret")
(bad / "pack.json").write_text(json.dumps({**good, "name": "local-bad", "install": [{"from": "../../../secret.txt", "to": "s.txt", "mode": "copy"}]}))
target = tmp / "target"
target.mkdir()
(target / "package.json").write_text("{}")
r = subprocess.run([sys.executable, str(HERE / "install.py"), str(bad), str(target), "--dry-run"], capture_output=True, text=True)
assert r.returncode != 0 and "outside the pack folder" in (r.stderr + r.stdout), r.stderr + r.stdout
assert not (target / "s.txt").exists()
print("ok")
