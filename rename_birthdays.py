"""Rename old BD collections to the existing HAPPY BIRTHDAY convention.

Run after media publishing has finished, since its snapshot stores source paths.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import build_remote
import server
import snapshot


PATTERN = re.compile(r"^(.+?)BD(20\d{2})$")
GROUPS = ("ANGERME", "つばきファクトリー")


def plan():
    folders = []
    for group in GROUPS:
        for source in (server.ROOT / group).iterdir():
            if not source.is_dir():
                continue
            match = PATTERN.fullmatch(source.name)
            if match is None:
                continue
            destination = source.with_name(f"HAPPY BIRTHDAY {match[1]} {match[2]}")
            if destination.exists():
                raise FileExistsError(destination)
            files = []
            for old in source.iterdir():
                if old.name.lower() == "desktop.ini":
                    continue
                if old.is_dir() or not old.name.startswith(source.name + "_"):
                    raise ValueError(f"Unexpected entry in {source}: {old.name}")
                new = old.with_name(destination.name + old.name[len(source.name):])
                if new.exists():
                    raise FileExistsError(new)
                files.append((old, new))
            folders.append((source, destination, files))
    return folders


def rename_and_refresh(folders):
    snapshot.load_or_create()
    planned_paths = {str(old) for _, _, files in folders for old, _ in files}
    snapshot_paths = {item["path"] for item in server.ITEMS}
    missing = planned_paths - snapshot_paths
    if missing:
        raise RuntimeError(f"Snapshot is missing {len(missing)} birthday files")
    event_keys = {(event["group"], event["name"]) for event in server.EVENTS}
    for source, _, _ in folders:
        if (source.parent.name, source.name) not in event_keys:
            raise RuntimeError(f"Snapshot is missing birthday event: {source}")
    changes = {}
    for source, destination, files in folders:
        for old, new in files:
            old.rename(new)
            changes[str(old)] = str(destination / new.name)
        source.rename(destination)

    changed_items = 0
    for item in server.ITEMS:
        replacement = changes.get(item["path"])
        if replacement:
            item["path"] = replacement
            item["name"] = Path(replacement).stem
            item["event"] = Path(replacement).parent.name
            changed_items += 1
    for event in server.EVENTS:
        for source, destination, _ in folders:
            if event["group"] == source.parent.name and event["name"] == source.name:
                event["name"] = destination.name
                break
    if changed_items != len(changes):
        raise RuntimeError(f"Snapshot mismatch: {changed_items} of {len(changes)} renamed files")
    snapshot.FILE.write_text(
        json.dumps({"items": server.ITEMS, "events": server.EVENTS}, ensure_ascii=False),
        encoding="utf-8",
    )
    build_remote.build(thumbnails=False)
    subprocess.run(["git", "add", "docs/catalog.json"], cwd=server.BASE, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=server.BASE).returncode:
        subprocess.run(["git", "commit", "-m", "Unify birthday collection names"], cwd=server.BASE, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=server.BASE, check=True)
    return changed_items


def update_public_catalog(folders):
    catalog_path = server.BASE / "docs" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    replacements = {(source.parent.name, source.name): destination.name
                    for source, destination, _ in folders}
    renamed = 0
    for item in catalog["items"]:
        old_event = item["event"]
        new_event = replacements.get((item["group"], old_event))
        if new_event:
            if not item["name"].startswith(old_event + "_"):
                raise ValueError(f"Unexpected catalog name: {item['name']}")
            item["event"] = new_event
            item["name"] = new_event + item["name"][len(old_event):]
            renamed += 1
    for event in catalog["events"]:
        event["name"] = replacements.get((event["group"], event["name"]), event["name"])
    expected = sum(len(files) for _, _, files in folders)
    if renamed != expected:
        raise RuntimeError(f"Catalog mismatch: {renamed} of {expected} files")
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    subprocess.run(["git", "add", "docs/catalog.json", "rename_birthdays.py"], cwd=server.BASE, check=True)
    subprocess.run(["git", "commit", "-m", "Unify birthday names in public catalog"], cwd=server.BASE, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=server.BASE, check=True)
    return renamed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply the rename; default is preview only")
    parser.add_argument("--catalog-only", action="store_true", help="Update public names before original upload completes")
    args = parser.parse_args()
    folders = plan()
    for source, destination, files in folders:
        print(f"{source} -> {destination} ({len(files)} files)")
    print(f"Total: {len(folders)} folders, {sum(len(files) for _, _, files in folders)} files")
    if args.apply:
        print(f"Renamed and published {rename_and_refresh(folders)} files")
    elif args.catalog_only:
        print(f"Updated {update_public_catalog(folders)} public item names")
