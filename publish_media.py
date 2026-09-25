"""Upload source media to per-group public GitHub repositories in resumable batches."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import server
import snapshot

OWNER = "ruli0618"
SLUGS = {
    "モーニング娘": "morning-musume",
    "ANGERME": "angerme",
    "Juice=Juice": "juice-juice",
    "つばきファクトリー": "tsubaki-factory",
    "BEYOOOOOONDS": "beyoooooonds",
    "OCHA NORMA": "ocha-norma",
    "ロージークロニクル": "rosy-chronicle",
    "研修生": "kenshusei",
    "M-LINE": "m-line",
}
LIMIT = 100_000_000
BATCH_BYTES = 450_000_000
WORK = server.BASE.parents[1] / "work" / "media-upload"


def run(*args, cwd=None, check=True):
    visible = " ".join(str(a) for a in args)
    print("$", visible[:180] + (" …" if len(visible) > 180 else ""), flush=True)
    retries = 4 if args[:2] == ("git", "push") else 1
    for attempt in range(retries):
        result = subprocess.run([str(a) for a in args], cwd=cwd, check=False, text=True)
        if result.returncode == 0 or not check:
            return result
        if attempt + 1 < retries:
            delay = 30 * (attempt + 1)
            print(f"Push failed; retrying in {delay}s ({attempt + 2}/{retries})", flush=True)
            time.sleep(delay)
    raise subprocess.CalledProcessError(result.returncode, [str(a) for a in args])


def upload_group(group):
    repo_name = "hellocolle-media-" + SLUGS[group]
    files = [x for x in server.ITEMS if x["group"] == group]
    expected = {f"media/{x['id']}{x['ext']}" for x in files}
    remote = subprocess.run(
        ["gh", "api", f"repos/{OWNER}/{repo_name}/git/trees/main?recursive=1"],
        capture_output=True, text=True,
    )
    if remote.returncode == 0:
        tree = json.loads(remote.stdout)
        remote_files = {entry["path"] for entry in tree["tree"]
                        if entry["path"].startswith("media/") and entry["type"] == "blob"}
        if remote_files == expected:
            print(f"Already complete {group}: {len(files)} files", flush=True)
            return WORK / SLUGS[group]
    folder = WORK / SLUGS[group]
    media_dir = folder / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    if not (folder / ".git").exists():
        run("git", "init", cwd=folder)
        run("git", "branch", "-M", "main", cwd=folder)
        run("git", "config", "pack.compression", "0", cwd=folder)
        run("git", "config", "core.compression", "0", cwd=folder)
        (folder / "README.md").write_text(f"# {group} collection media\n\nMedia files for [ハロコレ ビューア](https://github.com/{OWNER}/hellocolle-viewer). File names match IDs in the site catalog.\n", encoding="utf-8")
        run("git", "add", "README.md", cwd=folder)
        run("git", "commit", "-m", "Initialize media repository", cwd=folder)
        exists = subprocess.run(["gh", "repo", "view", f"{OWNER}/{repo_name}"], capture_output=True).returncode == 0
        if exists:
            run("git", "remote", "add", "origin", f"https://github.com/{OWNER}/{repo_name}.git", cwd=folder)
            run("git", "fetch", "origin", cwd=folder)
            run("git", "reset", "--hard", "origin/main", cwd=folder)
        else:
            run("gh", "repo", "create", f"{OWNER}/{repo_name}", "--public", "--source", ".", "--remote", "origin", "--push", cwd=folder)

    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=folder).returncode != 0:
        run("git", "commit", "--quiet", "-m", f"Resume interrupted {group} batch", cwd=folder)
    run("git", "push", "origin", "main", cwd=folder)
    tracked = set(subprocess.check_output(["git", "ls-files", "media"], cwd=folder, text=True).splitlines())
    pending = []
    batch_size = 0
    done = 0

    def push_batch():
        nonlocal pending, batch_size, done
        if not pending:
            return
        run("git", "add", "--", *pending, cwd=folder)
        if (folder / ".gitattributes").exists():
            run("git", "add", ".gitattributes", cwd=folder)
        run("git", "commit", "--quiet", "-m", f"Add {group} media batch ({len(pending)} files)", cwd=folder)
        run("git", "push", "origin", "main", cwd=folder)
        done += len(pending)
        print(f"{group}: uploaded {done} new files, {batch_size / 1e6:.0f} MB in last batch", flush=True)
        pending, batch_size = [], 0

    for item in files:
        rel = f"media/{item['id']}{item['ext']}"
        target = folder / rel
        if rel in tracked:
            continue
        if pending and batch_size + item["size"] > BATCH_BYTES:
            push_batch()
        if item["size"] >= LIMIT:
            run("git", "lfs", "track", rel, cwd=folder)
        if not target.exists() or target.stat().st_size != item["size"]:
            shutil.copy2(item["path"], target)
        pending.append(rel)
        batch_size += item["size"]
    push_batch()
    tree = json.loads(subprocess.check_output(["gh", "api", f"repos/{OWNER}/{repo_name}/git/trees/main?recursive=1"], text=True))
    remote_files = {entry["path"] for entry in tree["tree"] if entry["path"].startswith("media/") and entry["type"] == "blob"}
    expected = {f"media/{x['id']}{x['ext']}" for x in files}
    if remote_files != expected:
        raise RuntimeError(f"Remote count mismatch for {group}: {len(remote_files)} / {len(expected)}")
    print(f"Completed {group}: {len(files)} files", flush=True)
    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("groups", nargs="*", help="Group names; all by default")
    parser.add_argument("--cleanup", action="store_true", help="Delete verified local staging folders after each group")
    args = parser.parse_args()
    snapshot.load_or_create()
    for group in args.groups or server.GROUPS:
        if group not in SLUGS:
            sys.exit(f"Unknown group: {group}")
        folder = upload_group(group)
        if args.cleanup:
            root = WORK.resolve()
            destination = folder.resolve()
            if root not in destination.parents or destination == root:
                raise RuntimeError(f"Unsafe cleanup target: {destination}")
            shutil.rmtree(destination)
            print(f"Cleaned staging folder: {destination}", flush=True)
