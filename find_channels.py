"""Показывает, какие каналы чаще всего выдаются по нашим темам - чтобы выбрать белый список для sources.yaml."""
import collections
import sys
from urllib.parse import quote_plus

from yt_dlp import YoutubeDL

QUERIES = sys.argv[1:] or [
    "кс2 смешные моменты", "кс2 фейлы приколы", "кс2 открытие кейсов", "кс2 выпал нож",
    "кс2 лайфхаки", "кс2 фишки", "кс2 раскидки гайд", "кс2 клатч", "кс2 баги",
    "кс2 моменты со стримов", "кс2 нарезка стрима",
]

agg = collections.defaultdict(lambda: {"n": 0, "views": 0, "url": "", "titles": []})
with YoutubeDL({"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": 25}) as y:
    for q in QUERIES:
        try:
            r = y.extract_info(f"https://www.youtube.com/results?search_query={quote_plus(q)}&sp=EgIQAQ%253D%253D",
                               download=False)
        except Exception:
            continue
        for e in r.get("entries") or []:
            c = e.get("channel") or e.get("uploader")
            if not c:
                continue
            a = agg[c]
            a["n"] += 1
            a["views"] += e.get("view_count") or 0
            a["url"] = e.get("channel_url") or a["url"]
            if len(a["titles"]) < 2:
                a["titles"].append((e.get("title") or "")[:60])

for c, a in sorted(agg.items(), key=lambda x: (-x[1]["n"], -x[1]["views"]))[:25]:
    print(f"{c} | в выдаче: {a['n']} | просмотры: {a['views']:,} | {a['url']}")
    print("    ", " / ".join(a["titles"]))
