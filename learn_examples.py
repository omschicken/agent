"""Обучение на эталонном канале: подборки отобранных клипов -> профиль «хорошего момента» + образцы.

python learn_examples.py <ссылка на канал или видео> [сколько видео взять]

1. Берёт самые просматриваемые ролики канала (низкое качество, только для анализа, в репозиторий не попадает).
2. Режет на сцены (каждая сцена = один отобранный клип), расшифровывает речь, меряет звук.
3. Пишет examples/profile.json (статистика) и examples/ex_N.json + кадры (образцы для запросов Claude).
"""
import json
import os
import random
import statistics
import sys

import numpy as np
from yt_dlp import YoutubeDL

from agents import audio_events
from agents.curator import _cuts, _duration, _loudness
from agents.judge import _frames
from agents.transcribe import transcribe

MIN_SCENE = 12   # секунд: сцены короче в профиль и образцы не попадают
OUT = "examples"
SRC = os.path.join(OUT, "src")
os.makedirs(SRC, exist_ok=True)

url = sys.argv[1]
n_videos = int(sys.argv[2]) if len(sys.argv) > 2 else 5

# 1. выбираем самые просматриваемые ролики
with YoutubeDL({"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": 40}) as y:
    info = y.extract_info(url, download=False)
    if info.get("entries") is None:  # одно видео -> берём канал
        info = y.extract_info(info["channel_url"].rstrip("/") + "/videos", download=False)
    vids = [e for e in info["entries"] if e.get("id")]
vids.sort(key=lambda e: -(e.get("view_count") or 0))
vids = vids[:n_videos]

# 2. скачиваем
paths = []
for e in vids:
    p = os.path.join(SRC, f"{e['id']}.mp4")
    if not os.path.exists(p):
        with YoutubeDL({"quiet": True, "noprogress": True, "format": "bv*[height<=480]+ba/b[height<=480]",
                        "merge_output_format": "mp4", "outtmpl": os.path.join(SRC, "%(id)s.%(ext)s")}) as y:
            y.download([f"https://www.youtube.com/watch?v={e['id']}"])
    paths.append((p, e))
    print(f"[learn] {e['id']} {e.get('view_count')} просм. — {e.get('title')}")

# 3. анализ по сценам
scenes_all = []
for p, e in paths:
    dur = _duration(p)
    bounds = [0.0] + [c for c in _cuts(p, 0.3) if 0.5 < c < dur - 0.5] + [dur]
    loud = _loudness(p)
    med = statistics.median([m for _, m in loud]) if loud else -30
    segs = transcribe(p)
    for a, b in zip(bounds, bounds[1:]):
        s, t = a + 0.2, b - 0.2
        if t - s < MIN_SCENE:  # короткие вставки (5 с и т.п.) не учитываем: нужны законченные моменты 15-20 с
            continue
        pts = [(tt, m) for tt, m in loud if s <= tt <= t]
        if not pts:
            continue
        pk_t, pk = max(pts, key=lambda x: x[1])
        text = " ".join(x["text"] for x in segs if x["end"] >= s and x["start"] <= t).strip()
        scenes_all.append({"video": e["id"], "title": e.get("title"), "views": e.get("view_count"),
                           "start": round(s, 1), "end": round(t, 1), "dur": round(t - s, 1),
                           "peak_db": round(pk - med, 1), "peak_pos": round((pk_t - s) / (t - s), 2),
                           "speech": bool(text), "text": text[:400]})
    print(f"[learn] {e['id']}: сцен {sum(1 for x in scenes_all if x['video'] == e['id'])}")

# 4. профиль
def pct(vals, q):
    return round(float(np.percentile(vals, q)), 1) if vals else None

durs = [x["dur"] for x in scenes_all]
peaks = [x["peak_db"] for x in scenes_all]
profile = {
    "videos": len(paths), "scenes": len(scenes_all),
    "duration_sec": {"p10": pct(durs, 10), "median": pct(durs, 50), "p90": pct(durs, 90)},
    "peak_db_over_median": {"p10": pct(peaks, 10), "median": pct(peaks, 50), "p90": pct(peaks, 90)},
    "peak_position_in_clip": {"median": pct([x["peak_pos"] for x in scenes_all], 50)},
    "with_speech_ratio": round(sum(x["speech"] for x in scenes_all) / max(len(scenes_all), 1), 2),
}
json.dump(profile, open(os.path.join(OUT, "profile.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("[learn] профиль:", json.dumps(profile, ensure_ascii=False))

# 5. образцы: разные видео, 6-40 с, заметный пик, по возможности с речью
random.seed(7)
pool = [x for x in scenes_all if MIN_SCENE <= x["dur"] <= 30 and x["peak_db"] >= 8]
random.shuffle(pool)
pool.sort(key=lambda x: -(x["views"] or 0) * 0 + (0 if x["speech"] else 1))  # сначала с речью
picked, per_video = [], {}
for x in pool:
    if per_video.get(x["video"], 0) >= 2:
        continue
    picked.append(x)
    per_video[x["video"]] = per_video.get(x["video"], 0) + 1
    if len(picked) >= 8:
        break
import tempfile, shutil
for i, x in enumerate(picked):
    with tempfile.TemporaryDirectory() as tmp:
        fr = _frames(os.path.join(SRC, f"{x['video']}.mp4"), x["start"], x["end"], 3, tmp)
        for k, f in enumerate(fr):
            shutil.copy(f, os.path.join(OUT, f"ex_{i}_{k}.jpg"))
    json.dump(x, open(os.path.join(OUT, f"ex_{i}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[learn] образцов: {len(picked)}")
for i, x in enumerate(picked):
    print(f"  ex_{i}: {x['dur']}с пик +{x['peak_db']}дБ (на {x['peak_pos']:.0%}) | {x['text'][:90]}")
