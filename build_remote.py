"""Build the GitHub Pages site from the local source collection."""
from __future__ import annotations

import json
import argparse
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import publish_media
import catalog_rules
import server
import snapshot
from imaging import crop_thumbnail

import cv2

OWNER = publish_media.OWNER
DOCS = server.BASE / "docs"
THUMBS = DOCS / "thumbs"


def remote_url(item):
    name = f"{item['id']}{item['ext']}"
    repo = "hellocolle-media-" + publish_media.SLUGS[item["group"]]
    host = "media.githubusercontent.com/media" if item["size"] >= publish_media.LIMIT else "raw.githubusercontent.com"
    return f"https://{host}/{OWNER}/{repo}/main/media/{name}"


def make_thumb(item):
    target = THUMBS / f"{item['id']}.jpg"
    if target.exists():
        image = cv2.imread(str(target))
        if image is not None and image.shape[:2] == (360, 360):
            return True
    source = Path(item["path"])
    frame = None
    if item["kind"] == "video" and not target.exists():
        frame = THUMBS / f"{item['id']}.frame.jpg"
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "00:00:01",
                            "-i", item["path"], "-frames:v", "1", "-vf", "scale=700:-2",
                            "-q:v", "4", "-y", str(frame)], capture_output=True, timeout=35, check=True)
            source = frame
        except (OSError, subprocess.SubprocessError):
            return False
    elif item["kind"] == "video":
        source = target
    temporary = target.with_suffix(".new.jpg")
    try:
        if not crop_thumbnail(source, temporary, 360, 360):
            return False
        os.replace(temporary, target)
        return True
    finally:
        if frame is not None:
            frame.unlink(missing_ok=True)


def build(thumbnails=True):
    snapshot.load_or_create()
    DOCS.mkdir(exist_ok=True)
    THUMBS.mkdir(exist_ok=True)
    for name in ("index.html", "style.css", "app.js"):
        shutil.copy2(server.BASE / "static" / name, DOCS / name)
    (DOCS / ".nojekyll").touch()
    groups = [{"name": g, "count": sum(e["count"] for e in server.EVENTS if e["group"] == g),
               "events": sum(e["group"] == g for e in server.EVENTS)} for g in server.GROUPS]
    items = []
    for source in server.ITEMS:
        item = dict(server.public_item(source), url=remote_url(source))
        item["event"] = catalog_rules.event_name(source["event"])
        item["name"] = catalog_rules.item_name(item["name"], source["event"], item["event"])
        items.append(item)
    merged = {}
    for source in server.EVENTS:
        event = dict(source, name=catalog_rules.event_name(source["name"]))
        key = (event["group"], event["name"])
        if key in merged:
            for field in ("count", "photos", "videos"):
                merged[key][field] += event[field]
        else:
            merged[key] = event
    events = sorted(merged.values(), key=lambda e: (server.GROUPS.index(e["group"]), catalog_rules.event_sort_key(e)))
    catalog = {"groups": groups, "events": events, "total": len(items), "items": items}
    (DOCS / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Catalog: {len(items)} files, {len(server.EVENTS)} events", flush=True)
    if thumbnails:
        done = failed = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(make_thumb, x): x for x in server.ITEMS}
            for future in as_completed(futures):
                done += 1
                if not future.result():
                    failed += 1
                if done % 500 == 0 or done == len(items):
                    print(f"Thumbnails: {done}/{len(items)} ({failed} failures)", flush=True)
    print(f"Built Pages files in {DOCS}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-thumbs", action="store_true", help="Refresh catalog and frontend without regenerating thumbnails")
    args = parser.parse_args()
    build(not args.no_thumbs)
