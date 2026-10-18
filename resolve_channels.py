"""Находит YouTube-каналы по никам: для каждого ника показывает топ-кандидатов из поисковой выдачи."""
import collections
import sys
from urllib.parse import quote_plus

from yt_dlp import YoutubeDL

NAMES = sys.argv[1:]

with YoutubeDL({"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": 20}) as y:
    for name in NAMES:
        cands = collections.defaultdict(lambda: {"n": 0, "url": "", "title": ""})
        for q in (name, f"{name} cs2", f"{name} кс2"):
            try:
                r = y.extract_info(f"https://www.youtube.com/results?search_query={quote_plus(q)}&sp=EgIQAQ%253D%253D",
                                   download=False)
            except Exception:
                continue
            for e in r.get("entries") or []:
                c = e.get("channel") or e.get("uploader")
                if c:
                    d = cands[c]
                    d["n"] += 1
                    d["url"] = e.get("channel_url") or d["url"]
                    d["title"] = d["title"] or (e.get("title") or "")[:50]
        key = name.lower().replace("_", "").replace(" ", "")
        ranked = sorted(cands.items(), key=lambda x: (key not in x[0].lower().replace("_", "").replace(" ", ""), -x[1]["n"]))
        print(f"\n== {name}")
        for c, d in ranked[:4]:
            mark = "  <-- совпадает по имени" if key in c.lower().replace("_", "").replace(" ", "") else ""
            print(f"  {c} | {d['n']} видео в выдаче | {d['url']}{mark}")
