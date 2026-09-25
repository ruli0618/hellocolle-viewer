"""Conservative display names and human-friendly collection ordering."""
from __future__ import annotations

import re
import unicodedata


def event_name(value):
    name = unicodedata.normalize("NFC", value).replace("\u3000", " ").strip()
    name = re.sub(r"\s+", " ", name)
    birthday = re.fullmatch(r"HAPPY BIRTHDAY\s+(.+?)\s*(20\d{2})", name)
    if birthday:
        return f"HAPPY BIRTHDAY {birthday[1].strip()} {birthday[2]}"
    old_birthday = re.fullmatch(r"(.+?)BD(20\d{2})", name)
    if old_birthday:
        return f"HAPPY BIRTHDAY {old_birthday[1].strip()} {old_birthday[2]}"
    name = re.sub(r"^Graduation\s*〜\s*", "Graduation 〜", name)
    name = name.replace("エムハロ / エムハロイベント", "エムハロイベント")
    if " / " in name:
        parent, child = name.split(" / ", 1)
        if child.startswith(parent):
            suffix = child[len(parent):].lstrip()
            name = parent + " " + suffix
    name = name.replace("BEYOOOOONDSCHICA#TETSU", "BEYOOOOONDS CHICA#TETSU")
    name = name.replace("BEYOOOOONDS_CHICA#TETSU", "BEYOOOOONDS CHICA#TETSU")
    name = name.replace("BEYOOOOONDSSeasoningS", "BEYOOOOONDS SeasoningS")
    name = name.replace("BEYOOOOONDS雨ノ森", "BEYOOOOONDS 雨ノ森")
    name = re.sub(r"(?<![\s/])FCイベント", " FCイベント", name)
    name = re.sub(r"FCイベント\s*(20\d{2})", r"FCイベント \1", name)
    name = re.sub(r"(?i)\bvol\.\s*(\d+)", lambda m: f"vol.{int(m[1])}", name)
    return re.sub(r"\s+", " ", name).strip()


def item_name(name, old_event, new_event):
    if new_event.startswith("HAPPY BIRTHDAY ") and name.startswith(old_event + "_"):
        return new_event + name[len(old_event):]
    return name


def natural(value):
    return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                 for part in re.split(r"(\d+)", value) if part)


def event_sort_key(event):
    name = event["name"]
    if name.startswith("HAPPY BIRTHDAY "):
        match = re.fullmatch(r"HAPPY BIRTHDAY (.+) (20\d{2})", name)
        if match:
            return (0, natural(match[1]), int(match[2]), ())
    if name.startswith("Graduation "):
        return (1, natural(name), 0, ())
    if "FCイベント" in name or "ファンクラブ" in name or name.startswith("エムハロイベント"):
        category = 2
    elif re.search(r"コンサート|CONCERT|LIVE|ライブ|ツアー|TOUR", name, re.I):
        category = 3
    elif name.startswith("Hello! Project Official Shop"):
        category = 4
    else:
        category = 5
    # Nearby editions stay together; years and volumes use numeric order.
    series = re.split(r"[～〜「『]", name, 1)[0]
    series = re.sub(r"20\d{2}", "", series)
    series = re.sub(r"(?i)vol\.\d+", "vol.", series).strip()
    return (category, natural(series), 0, natural(name))
