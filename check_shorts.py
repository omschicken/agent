"""Показывает, что лежит во вкладках Shorts каналов из sources.yaml (сколько роликов, какой длины)."""
import yaml
from yt_dlp import YoutubeDL

channels = yaml.safe_load(open("sources.yaml", encoding="utf-8"))["channels"]
with YoutubeDL({"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": 4}) as y:
    for u in channels:
        try:
            r = y.extract_info(u, download=False)
        except Exception as e:
            print(u[-45:], "ERR", str(e)[:70])
            continue
        es = r.get("entries") or []
        sample = " ; ".join(f"{(e.get('title') or '')[:38]} ({e.get('duration')}с)" for e in es[:2])
        print(f"{(r.get('title') or u[-30:])[:30]} | {len(es)} шт | {sample}")
