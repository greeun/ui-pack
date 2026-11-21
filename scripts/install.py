#!/usr/bin/env python3
"""Install a UI pack's files into a target project (the mechanical part only). It does not convert any screen.

Usage:
  python3 install.py <pack folder> <target project> [--without jobs] [--name product-name] [--keep-defaults] [--dry-run]

What it does:
  1. Compares pack.json `requires` with the target's package.json and stops when they do not match.
  2. Copies files as listed in `install`. {src} is `src` when the target has a src/ folder, otherwise the project root.
     - A file that already exists in the target is kept as <name>.before-pack before it is overwritten
       (skipped when the content is identical).
     - A file whose mode is `merge` (the layout) is not copied; it is placed next to the target file as
       <name>.pack-example for a person to merge.
     - A file whose mode is `copy-if-missing` is skipped when the target already has a file with the same name
       (any extension).
     - Copied files get the current time as their modification time (so the dev server notices the change).
  3. Files of an optional group excluded with --without are not copied.
  4. With --name, replaces productName in ui-pack-config.ts.
  5. Installs `dependencies` and `devDependencies` with the target's package manager. When the package manager
     reports a failure but every package is in node_modules (pnpm 11 "ignored build scripts", for example),
     it says so and continues.
  6. Writes ui-pack.lock.json (installed files and content hashes) in the target root. On a later run this record
     - keeps files the user edited after the install (config, design guide, merged globals.css ...) untouched, and
     - replaces only unedited files with the pack's new content. Installing the same pack twice therefore changes
       no file the second time.
  7. With --keep-defaults, installs globals.css without the lines that clear the Tailwind default tokens
     (--color-*: initial and so on). Use it when the pack is applied to only some screens and the other screens
     must keep using the default color and shadow classes.
  8. Deletes the .next build cache, so stale CSS is not served from it (it is rebuilt on the next start).
At the end it prints what it did and what a person has to do next.
"""
import argparse, hashlib, json, pathlib, re, shutil, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("pack")
ap.add_argument("target")
ap.add_argument("--without", default="", help="optional groups to leave out, comma separated (e.g. jobs)")
ap.add_argument("--name", default=None, help="productName in ui-pack-config")
ap.add_argument("--keep-defaults", action="store_true", help="keep the Tailwind default tokens (when applying to some screens only)")
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()

pack = pathlib.Path(a.pack).expanduser().resolve()
target = pathlib.Path(a.target).expanduser().resolve()
meta = json.loads((pack / "pack.json").read_text())
pkg_path = target / "package.json"
if not pkg_path.exists():
    sys.exit(f"The target has no package.json: {target}")
pkg = json.loads(pkg_path.read_text())
deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
LOCK = target / "ui-pack.lock.json"
lock = json.loads(LOCK.read_text()) if LOCK.exists() else {"pack": meta["name"], "files": {}}
new_lock = {"pack": meta["name"], "version": meta["version"], "files": dict(lock.get("files", {}))}

# 1. Required stack: only the major version is compared.
def major(v: str) -> int | None:
    digits = "".join(ch if ch.isdigit() or ch == "." else " " for ch in v).split()
    return int(digits[0].split(".")[0]) if digits else None

problems = []
for name in ("react", "next", "tailwindcss"):
    need = meta["requires"].get(name)
    if not need:
        continue
    have = deps.get(name)
    if have is None:
        problems.append(f"{name}: missing in the target (needs {need})")
        continue
    have_major, need_major = major(have), major(need)
    if have_major is not None and need_major is not None and have_major < need_major:
        problems.append(f"{name}: target has {have}, needs {need}")
if problems:
    print("Stopping: the required stack does not match. Follow 'When the stack differs' in SKILL.md.")
    print("\n".join("  - " + p for p in problems))
    sys.exit(2)

src_root = "src" if (target / "src").is_dir() else "."
excluded = set()
for group in filter(None, a.without.split(",")):
    files = meta.get("optional", {}).get(group)
    if files is None:
        # A pack without that group (e.g. a pack with no background-job components) has nothing to leave out. Do not stop.
        print(f"This pack has no optional group '{group}'. Nothing to leave out; continuing.")
        continue
    excluded.update(files)

done, kept, skipped, merge_todo, customized = [], [], [], [], []


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def content_for(src: pathlib.Path, rel_pack: str) -> bytes:
    """The content to install. Every adjustment for the target happens here and nowhere else."""
    if not src.exists():
        sys.exit(f"The pack has no such file: {rel_pack}  (create the files listed in pack.json `install` first)")
    data = src.read_bytes()
    if a.keep_defaults and rel_pack == "tokens/globals.css":
        text = data.decode()
        text = re.sub(r"^(\s*)(--(?:color|text|radius|shadow)-\*: initial;)",
                      r"\1/* ui-pack: keep-defaults (keeps the Tailwind default tokens while only some screens use the pack) \2 */", text, flags=re.M)
        data = text.encode()
    if src_root == "." and rel_pack.startswith("tests/"):
        data = data.decode().replace('"../src/app/globals.css"', '"../app/globals.css"').encode()
    return data


def place(src: pathlib.Path, dst: pathlib.Path, mode: str):
    rel_pack = str(src.relative_to(pack))
    rel_dst = str(dst.relative_to(target))
    if rel_pack in excluded:
        skipped.append(f"{rel_pack} (--without)")
        return
    data = content_for(src, rel_pack)
    if mode == "merge":
        if rel_dst in lock["files"]:
            return  # already merged once
        ex = dst.with_name(dst.name + ".pack-example")
        merge_todo.append(f"{rel_dst} ← merge by hand, using {ex.relative_to(target)} as the example")
        new_lock["files"][rel_dst] = "merged"
        dst = ex
    elif mode == "copy-if-missing" and rel_dst not in lock["files"]:
        stem = dst.name.split(".")[0] + "."
        if any(p.name.startswith(stem) for p in dst.parent.glob("*") if p.is_file()):
            skipped.append(f"{rel_dst} (already exists)")
            return
    if dst.exists() and mode != "merge":
        current = dst.read_bytes()
        if current == data:
            new_lock["files"][rel_dst] = sha(data)
            return
        installed = lock["files"].get(rel_dst)
        if installed is not None and installed != sha(current):
            customized.append(rel_dst)  # edited by the user after the install
            return
        backup = dst.with_name(dst.name + ".before-pack")
        if installed is None:
            kept.append(f"{rel_dst} → {backup.name}")
            if not a.dry_run:
                shutil.copyfile(dst, backup)
    done.append(rel_dst)
    new_lock["files"][rel_dst] = sha(data)
    if not a.dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)  # the modification time becomes now


# 2. Copy files
for entry in meta["install"]:
    src = pack / entry["from"]
    dst_rel = entry["to"].replace("{src}", src_root)
    dst = (target / dst_rel).resolve()
    mode = entry["mode"]
    if entry["from"].endswith("/"):
        for f in sorted(src.rglob("*")):
            if f.is_file():
                place(f, dst / f.relative_to(src), "copy")
    else:
        place(src, dst, mode)

# 4. Product name (done before the dependencies so it is set even when their install fails)
cfg = target / meta["config"].replace("{src}", src_root)
cfg_rel = str(cfg.relative_to(target))
if a.name and cfg.exists() and not a.dry_run and cfg_rel not in customized:
    text = cfg.read_text()
    changed = text.replace('productName: "my-app"', f'productName: {json.dumps(a.name, ensure_ascii=False)}', 1)
    if changed != text:
        cfg.write_text(changed)
        new_lock["files"][cfg_rel] = sha(changed.encode())


# 5. Install dependencies
def manager() -> str:
    for lockfile, cmd in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lock", "bun"), ("bun.lockb", "bun")):
        if (target / lockfile).exists():
            return cmd
    return "npm"


def installed(name: str) -> bool:
    return (target / "node_modules" / name / "package.json").exists()


pm = manager()
add = "install" if pm == "npm" else "add"
need_deps = [f"{n}@{v}" for n, v in meta.get("dependencies", {}).items() if n not in deps]
need_dev = [f"{n}@{v}" for n, v in meta.get("devDependencies", {}).items() if n not in deps]
dep_warnings = []
for group, flag in ((need_deps, []), (need_dev, ["-D"])):
    if not group:
        continue
    cmd = [pm, add, *flag, *group]
    print("$", " ".join(cmd))
    if a.dry_run:
        continue
    r = subprocess.run(cmd, cwd=target)
    names = [g.rsplit("@", 1)[0] for g in group]
    missing = [n for n in names if not installed(n)]
    if missing:
        sys.exit(f"Package install failed: {', '.join(missing)} (exit code {r.returncode})")
    if r.returncode != 0:
        dep_warnings.append(f"{' '.join(cmd)} exited with code {r.returncode}, but every package is installed. "
                            "If this is the pnpm 11 'ignored build scripts' warning, the user decides allowBuilds in pnpm-workspace.yaml")

# 7. Dev server cache: stops a stale globals.css from being served from the cache. .next is a build cache that is
#    rebuilt, so it is deleted (moving it aside would make eslint and other tools scan that folder too).
next_dir = target / ".next"
if done and next_dir.is_dir() and not a.dry_run:
    shutil.rmtree(next_dir)
    print("Deleted the .next build cache (it is rebuilt when the dev server restarts)")

if not a.dry_run:
    LOCK.write_text(json.dumps(new_lock, ensure_ascii=False, indent=2) + "\n")

print(f"\n[{meta['name']} {meta['version']}] source root: {src_root}  package manager: {pm}{'  (dry-run)' if a.dry_run else ''}"
      f"{'  keep-defaults' if a.keep_defaults else ''}")
print(f"{'Would copy' if a.dry_run else 'Copied'} {len(done)} files")
if kept:
    print("Original files kept before overwriting:\n" + "\n".join("  - " + k for k in kept))
if customized:
    print("Files left untouched because they were edited after the install:\n" + "\n".join("  - " + c for c in customized))
if skipped:
    print("Skipped files:\n" + "\n".join("  - " + s for s in skipped))
for w in dep_warnings:
    print("Warning: " + w)
print("\nNext steps:")
for m in merge_todo:
    print("  - " + m)
if not lock["files"]:
    print(f"  - Set the values in {cfg_rel} for the target app")
    print("  - Restart any running dev server (it does not pick up the replaced globals.css)")
    print("  - Continue with 'Convert the screens' and 'Verify' in SKILL.md")
    print("  - Commit ui-pack.lock.json (it protects edited files on a later install)")
