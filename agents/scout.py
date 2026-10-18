"""Разведчик: сам ищет и скачивает видео для нарезки.

Источники:
  - поисковые запросы YouTube (config.yaml -> scout.queries), сортировка по просмотрам за свежий период
  - sources.yaml: channels (каналы/плейлисты) и urls (любые ссылки, что понимает yt-dlp: YouTube, Twitch, X, Reddit...)
  - sources.yaml: blocklist - каналы, которые не трогаем (например, попросили убрать)
Рядом с видео пишется <id>.txt с названием и источником (идёт в тексты постов).
"""
import json
import os
import re
from urllib.parse import quote_plus

import yaml
from yt_dlp import YoutubeDL

SEEN = "seen.json"
# sp-параметры поиска YouTube: фильтр "эта неделя/месяц" + сортировка по просмотрам
SP = {"week": "CAMSBAgDEAE%253D", "month": "CAMSBAgEEAE%253D", "any": "CAMSAhAB"}


def _seen():
    return set(json.load(open(SEEN, encoding="utf-8"))) if os.path.exists(SEEN) else set()


def _save_seen(s):
    json.dump(sorted(s), open(SEEN, "w", encoding="utf-8"))


def _info(url, **opts):
    with YoutubeDL({"quiet": True, "skip_download": True, "noprogress": True, **opts}) as y:
        return y.extract_info(url, download=False)


def _search(query, limit, period):
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={SP.get(period, SP['any'])}"
    res = _info(url, extract_flat=True, playlistend=limit)
    return [(e["id"], f"https://www.youtube.com/watch?v={e['id']}") for e in (res.get("entries") or []) if e.get("id")]


def _from_sources(path, limit):
    if not os.path.exists(path):
        return [], set()
    cfg = yaml.safe_load(open(path, encoding="utf-8")) or {}
    out = []
    for url in cfg.get("channels", []) + cfg.get("urls", []):
        try:
            res = _info(url, extract_flat=True, playlistend=limit)
        except Exception as e:
            print(f"[scout] {url}: пропуск ({e})")
            continue
        for e in res.get("entries") or [res]:
            if e.get("id"):
                out.append((e["id"], e.get("url") or e.get("webpage_url") or url))
    return out, {b.lower() for b in cfg.get("blocklist", [])}


def _download(url, dest, max_height):
    opts = {
        "quiet": True, "noprogress": True,
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(dest, "%(id)s.%(ext)s"),
    }
    with YoutubeDL(opts) as y:
        y.download([url])


def scout(cfg, dest="inbox", sources_file="sources.yaml"):
    sc = cfg.get("scout", {})
    seen = _seen()
    cands, blocked = _from_sources(sources_file, sc.get("per_query", 8))
    for q in sc.get("queries", []):
        cands += _search(q, sc.get("per_query", 8), sc.get("period", "week"))

    got = 0
    for vid, url in dict(cands).items():
        if vid in seen:
            continue
        if got >= sc.get("max_new_videos", 3):
            break
        try:
            m = _info(url)
        except Exception as e:
            print(f"[scout] {vid}: пропуск ({e})")
            continue
        seen.add(vid)
        author = (m.get("uploader") or m.get("channel") or "").lower()
        if any(b in author for b in blocked):
            continue
        if not (sc.get("min_duration", 60) <= (m.get("duration") or 0) <= sc.get("max_duration", 1800)):
            continue
        if (m.get("view_count") or 0) < sc.get("min_views", 0):
            continue
        title = (m.get("title") or "").lower()
        bad = next((x for x in sc.get("exclude", []) if x.lower() in title), None)
        if not bad and re.search(r"#\s?\d+|episode \d+|part \d+|vol\.? ?\d+", title):
            bad = "номер выпуска (серия-сборник)"
        if bad:
            print(f"[scout] {vid}: сборка/нерелевантно ('{bad}'), пропуск — {m.get('title')}")
            continue
        kws = [k.lower() for k in sc.get("keywords", [])]
        text = " ".join([m.get("title") or "", " ".join(m.get("tags") or [])]).lower()
        if kws and not any(k in text for k in kws):
            print(f"[scout] {vid}: не про CS, пропуск — {m.get('title')}")
            continue
        _download(url, dest, sc.get("max_height", 1080))
        credit = (
            f"{m.get('title')}\n"
            f"Источник: «{m.get('title')}», канал {m.get('uploader')}, {m.get('webpage_url')}"
        )
        # имя файла берём как скачал yt-dlp (id.ext), заметку кладём рядом
        open(os.path.join(dest, f"{m['id']}.txt"), "w", encoding="utf-8").write(credit)
        got += 1
        print(f"[scout] скачано: {m['id']} — {m.get('title')}")
    _save_seen(seen)
    return got
