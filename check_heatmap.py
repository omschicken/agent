"""Проверка: есть ли у популярных видео каналов кривая «Most replayed» (heatmap) и какие там пики."""
import sys

import yaml
from yt_dlp import YoutubeDL

channels = yaml.safe_load(open("sources.yaml", encoding="utf-8"))["channels"]
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 3
with YoutubeDL({"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": limit}) as flat, \
        YoutubeDL({"quiet": True, "skip_download": True}) as full:
    for u in channels:
        url = u.split("?")[0] + "?view=0&sort=p"  # сортировка по популярности
        try:
            es = flat.extract_info(url, download=False).get("entries") or []
        except Exception as e:
            print(f"{u[-40:]}: ERR {str(e)[:60]}")
            continue
        for e in es[:limit]:
            try:
                m = full.extract_info(e["url"], download=False)
            except Exception as ex:
                print("   ERR", str(ex)[:60])
                continue
            hm = m.get("heatmap") or []
            top = sorted(hm, key=lambda b: -b["value"])[:3]
            peaks = ", ".join(f"{b['start_time']:.0f}-{b['end_time']:.0f}с ({b['value']:.2f})" for b in top)
            print(f"{(m.get('channel') or '')[:22]:22} | {m.get('duration') or 0:5.0f}с | {m.get('view_count') or 0:>9,} | "
                  f"{'heatmap ' + str(len(hm)) if hm else 'нет heatmap':13} | {(m.get('title') or '')[:48]} | {peaks}")
