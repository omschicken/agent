"""Куратор: режет видео по границам сцен, чтобы клип не захватывал соседний момент.

1. ffmpeg находит склейки (scene change) -> видео делится на сегменты-сцены.
2. Для каждой сцены считаем громкость (ebur128): пик и среднее.
3. Берём лучшие сцены; клип = сцена целиком (без первых/последних кадров перехода).
   Если сцена длиннее max_sec - окно вокруг самого громкого места внутри сцены.
   Видео без склеек (Twitch-клип, один момент) - одна сцена.
"""
import re
from agents.proc import run

EDGE = 0.25  # отступ от склейки, чтобы не ловить кадры перехода


def _duration(path):
    out = run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    ).stdout
    return float(out.strip())


def _cuts(path, threshold):
    """Склейки + границы чёрных кадров/титульных карточек (плавные переходы между моментами)."""
    p = run(
        ["ffmpeg", "-i", path, "-an", "-vf",
         f"blackdetect=d=0.1:pic_th=0.9:pix_th=0.2,select='gt(scene,{threshold})',showinfo",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    cuts = [float(t) for t in re.findall(r"pts_time:([\d.]+)", p.stderr)]
    for s, e in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", p.stderr):
        cuts += [float(s), float(e)]
    return sorted(cuts)


def _loudness(path):
    p = run(
        ["ffmpeg", "-i", path, "-vn", "-af", "ebur128=peak=none", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return [
        (float(t), float(m))
        for t, m in re.findall(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+)", p.stderr)
        if float(m) > -120
    ]


def find_highlights(path, min_sec, max_sec, n, scene_threshold=0.3):
    dur = _duration(path)
    bounds = [0.0] + [c for c in _cuts(path, scene_threshold) if 0.5 < c < dur - 0.5] + [dur]
    loud = _loudness(path)

    scored = []
    for a, b in zip(bounds, bounds[1:]):
        start, end = a + (EDGE if a > 0 else 0), b - (EDGE if b < dur else 0)
        if end - start < min_sec:
            continue
        pts = [(t, m) for t, m in loud if start <= t <= end]
        peak_t, peak = max(pts, key=lambda x: x[1]) if pts else ((start + end) / 2, -70)
        if end - start > max_sec:  # длинная сцена: окно вокруг пика, внутри сцены
            s = min(max(start, peak_t - max_sec * 0.6), end - max_sec)
            start, end = s, s + max_sec
        scored.append((peak, start, end))

    best = sorted(scored, reverse=True)[:n]
    return sorted((round(s, 2), round(e, 2)) for _, s, e in best)
