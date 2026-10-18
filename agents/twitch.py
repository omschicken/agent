"""Twitch-разведчик: топ-клипы зрителей = момент, который аудитория выбрала сама.

Берём из клипа только ВРЕМЯ в записи стрима (VOD + секунда), а сам момент вырезаем из записи стрима
с подводкой и хвостом - то есть это нарезка стрима, а не перезалив чужого клипа.
"""
import json
import os
import time
import urllib.request

from yt_dlp import YoutubeDL
from yt_dlp.utils import download_range_func

GQL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # публичный web-клиент Twitch (его использует сам сайт twitch.tv)
SEEN = "seen_twitch.json"

QUERY = """query($login:String!, $period:ClipsPeriod!, $n:Int!){
  user(login:$login){ displayName
    clips(first:$n, criteria:{period:$period, sort:VIEWS_DESC}){
      edges{ node{ slug title viewCount durationSeconds createdAt url
                   game{ name } videoOffsetSeconds video{ id } } } } } }"""


def top_clips(login, period="LAST_WEEK", n=20):
    body = json.dumps({"query": QUERY, "variables": {"login": login, "period": period, "n": n}}).encode()
    req = urllib.request.Request(GQL, body, {"Client-ID": CLIENT_ID, "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            r = json.load(urllib.request.urlopen(req, timeout=30))
            u = (r.get("data") or {}).get("user")
            return [e["node"] for e in (u["clips"]["edges"] if u else [])]
        except Exception as e:
            if attempt == 2:
                print(f"[twitch] {login}: ошибка ({str(e)[:80]})")
            time.sleep(2)
    return []


def _download_segment(vod_id, start, end, out_path, max_height):
    opts = {
        "quiet": True, "noprogress": True,
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
        "merge_output_format": "mp4",
        "download_ranges": download_range_func(None, [(start, end)]),
        "force_keyframes_at_cuts": True,
        "outtmpl": out_path,
    }
    with YoutubeDL(opts) as y:
        y.download([f"https://www.twitch.tv/videos/{vod_id}"])


def scout(cfg, dest="inbox"):
    tw = cfg.get("twitch", {})
    seen = set(json.load(open(SEEN, encoding="utf-8"))) if os.path.exists(SEEN) else set()
    jobs = []
    for login in tw.get("logins", []):
        clips = top_clips(login, tw.get("period", "LAST_WEEK"))
        good = [c for c in clips
                if (c.get("video") or {}).get("id") and c.get("videoOffsetSeconds") is not None
                and tw.get("game_contains", "counter-strike") in ((c.get("game") or {}).get("name") or "").lower()
                and c["viewCount"] >= tw.get("min_views", 500)]
        for c in good[: tw.get("per_channel", 3)]:
            jobs.append((c["viewCount"], login, c))
    jobs.sort(key=lambda j: -j[0])

    lead, tail = tw.get("lead", 12), tw.get("tail", 6)
    got = 0
    for views, login, c in jobs:
        if got >= tw.get("max_new", 10):
            break
        vod, off = c["video"]["id"], int(c["videoOffsetSeconds"])
        key = f"{vod}_{off // 30}"  # соседние клипы на одном месте не дублируем
        if key in seen or f"{vod}_{off // 30 - 1}" in seen:
            continue
        seen.add(key)
        start, end = max(0, off - lead), off + int(c["durationSeconds"]) + tail
        name = f"tw_{login}_{vod}_{start}"
        out = os.path.join(dest, name + ".mp4")
        try:
            _download_segment(vod, start, end, out, tw.get("max_height", 720))
        except Exception as e:
            print(f"[twitch] {name}: не скачалось ({str(e)[:100]})")
            continue
        if not os.path.exists(out):
            print(f"[twitch] {name}: файл не появился (запись удалена или только для подписчиков?)")
            continue
        credit = (f"{c['title']}\nИсточник: стрим {login} на Twitch, момент по отметке зрителей "
                  f"({views} просмотров клипа), https://www.twitch.tv/videos/{vod}?t={off}s")
        open(os.path.join(dest, name + ".txt"), "w", encoding="utf-8").write(credit)
        json.dump({"type": "segment", "login": login, "views": views, "lead": lead, "clip_title": c["title"]},
                  open(os.path.join(dest, name + ".seg.json"), "w", encoding="utf-8"), ensure_ascii=False)
        got += 1
        print(f"[twitch] {name}: {views} просм. «{c['title']}» ({end - start}с)")
    json.dump(sorted(seen), open(SEEN, "w", encoding="utf-8"))
    return got
