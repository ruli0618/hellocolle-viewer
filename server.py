"""Local Hello! Collection viewer. Run with: python server.py"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from imaging import crop_thumbnail

ROOT = Path(r"E:\ハロコレ")
GROUPS = ["モーニング娘", "ANGERME", "Juice=Juice", "つばきファクトリー", "BEYOOOOOONDS", "OCHA NORMA", "ロージークロニクル", "研修生", "M-LINE"]
BASE = Path(__file__).resolve().parent
CACHE = BASE / "work" / "thumbnails"
ITEMS = []
EVENTS = []
LOCK = threading.Lock()


def scan():
    items, events = [], []
    for group in GROUPS:
        folder = ROOT / group
        if not folder.is_dir():
            continue
        grouped = {}
        for path in sorted(folder.rglob("*"), key=lambda p: str(p).casefold()):
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".mp4"}:
                continue
            rel = path.relative_to(folder)
            event = " / ".join(rel.parts[:-1]) if len(rel.parts) > 1 else "その他"
            kind = "video" if path.suffix.lower() == ".mp4" else "photo"
            item = {"id": len(items), "group": group, "event": event, "name": path.stem, "ext": path.suffix.lower(),
                    "kind": kind, "size": path.stat().st_size, "path": str(path)}
            items.append(item)
            grouped.setdefault(event, []).append(item)
        for event, files in grouped.items():
            cover = next((x for x in files if x["kind"] == "photo"), files[0])
            events.append({"group": group, "name": event, "count": len(files),
                           "photos": sum(x["kind"] == "photo" for x in files),
                           "videos": sum(x["kind"] == "video" for x in files),
                           "cover": cover["id"]})
    with LOCK:
        ITEMS[:] = items
        EVENTS[:] = events


def public_item(item):
    result = {key: item[key] for key in ("id", "group", "event", "name", "ext", "kind", "size")}
    rarity = re.search(r"★\s*([1-5])", item["name"])
    result["rarity"] = int(rarity.group(1)) if rarity else None
    parts = item["name"].split("_")
    member = parts[-1] if len(parts) > 1 else item["name"]
    if re.fullmatch(r"[a-z0-9]{5,10}", member, re.IGNORECASE) and len(parts) > 2:
        member = parts[-2]
    member = re.sub(r"^☆\d+-\d+", "", member)
    result["member"] = member
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args))

    def send_json(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path, content_type=None, range_support=False, cache=True):
        size = path.stat().st_size
        start, end = 0, size - 1
        header = self.headers.get("Range", "") if range_support else ""
        if header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
            if not match:
                self.send_error(416)
                return
            a, b = match.groups()
            if not a and not b:
                self.send_error(416)
                return
            if a:
                start = int(a)
                end = min(int(b), end) if b else end
            else:
                start = max(0, size - int(b))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        length = end - start + 1
        self.send_response(206 if header else 200)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes" if range_support else "none")
        if header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-store")
        self.end_headers()
        try:
            with path.open("rb") as f:
                f.seek(start)
                while length:
                    chunk = f.read(min(length, 1024 * 1024))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    length -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        if route == "/api/catalog":
            self.send_json({"groups": [{"name": g, "count": sum(e["count"] for e in EVENTS if e["group"] == g),
                                         "events": sum(e["group"] == g for e in EVENTS)} for g in GROUPS],
                            "events": EVENTS, "total": len(ITEMS)})
            return
        if route == "/api/items":
            group = query.get("group", [""])[0]
            event = query.get("event", [""])[0]
            kind = query.get("kind", [""])[0]
            favorite_ids = query.get("favorites", [""])[0]
            selected = {int(v) for v in favorite_ids.split(",") if v.isdigit()} if kind == "favorite" else None
            term = query.get("q", [""])[0].casefold().strip()
            try:
                page = max(0, int(query.get("page", ["0"])[0]))
            except ValueError:
                page = 0
            matches = [x for x in ITEMS if (not group or x["group"] == group)
                       and (not event or x["event"] == event)
                       and (not kind or x["kind"] == kind)
                       and (selected is None or x["id"] in selected)
                       and (not term or term in (x["group"] + " " + x["event"] + " " + x["name"]).casefold())]
            size = 72
            self.send_json({"items": [public_item(x) for x in matches[page * size:(page + 1) * size]],
                            "total": len(matches), "page": page, "hasMore": (page + 1) * size < len(matches)})
            return
        match = re.fullmatch(r"/media/(\d+)", route)
        if match:
            idx = int(match.group(1))
            if idx >= len(ITEMS):
                self.send_error(404)
                return
            item = ITEMS[idx]
            path = Path(item["path"])
            if not path.is_file():
                self.send_error(404)
                return
            self.send_file(path, range_support=item["kind"] == "video")
            return
        match = re.fullmatch(r"/(thumb|cover)/(\d+)", route)
        if match:
            view, idx = match.group(1), int(match.group(2))
            if idx >= len(ITEMS):
                self.send_error(404)
                return
            item = ITEMS[idx]
            CACHE.mkdir(parents=True, exist_ok=True)
            signature = hashlib.sha256((item["path"] + str(Path(item["path"]).stat().st_mtime_ns)).encode("utf-8")).hexdigest()[:20]
            target = CACHE / f"{signature}-{view}-v2.jpg"
            if not target.is_file():
                source = Path(item["path"])
                if item["kind"] == "video":
                    source = CACHE / f"{signature}-frame.jpg"
                    if not source.exists():
                        try:
                            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "00:00:01",
                                            "-i", item["path"], "-frames:v", "1", "-vf", "scale=700:-2",
                                            "-q:v", "4", "-y", str(source)], stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, timeout=25, check=True)
                        except (OSError, subprocess.SubprocessError):
                            self.send_error(404)
                            return
                width, height = (560, 320) if view == "cover" else (360, 360)
                if not crop_thumbnail(source, target, width, height):
                    self.send_error(404)
                    return
            self.send_file(target, "image/jpeg")
            return
        if route == "/api/rescan":
            scan()
            self.send_json({"total": len(ITEMS)})
            return
        static = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
        if route in static:
            self.send_file(BASE / "static" / static[route], cache=False)
            return
        self.send_error(404)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 for access from your phone on the same Wi-Fi")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    scan()
    print(f"Indexed {len(ITEMS)} files in {len(EVENTS)} events", flush=True)
    print(f"Open http://{args.host}:{args.port}", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
