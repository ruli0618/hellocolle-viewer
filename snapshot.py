"""Keep media IDs stable across long, resumable uploads."""
from __future__ import annotations

import json

import server

FILE = server.BASE / "work" / "collection-snapshot.json"


def load_or_create():
    if FILE.exists():
        data = json.loads(FILE.read_text(encoding="utf-8"))
        server.ITEMS[:] = data["items"]
        server.EVENTS[:] = data["events"]
        return
    server.scan()
    FILE.parent.mkdir(exist_ok=True)
    FILE.write_text(json.dumps({"items": server.ITEMS, "events": server.EVENTS}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    load_or_create()
    print(f"Snapshot: {len(server.ITEMS)} files, {len(server.EVENTS)} events")
