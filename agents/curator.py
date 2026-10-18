"""Находит кандидаты в хайлайты: пики громкости (крики, выстрелы, реакция)."""
import re
import subprocess


def _duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    ).stdout
    return float(out.strip())


def find_highlights(path, min_sec, max_sec, n):
    """Momentary loudness (ebur128) -> топ-N непересекающихся пиков -> окна [start, end]."""
    p = subprocess.run(
        ["ffmpeg", "-i", path, "-af", "ebur128=peak=none", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    pts = [
        (float(t), float(m))
        for t, m in re.findall(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+)", p.stderr)
    ]
    dur = _duration(path)
    picked = []
    for t, m in sorted(pts, key=lambda x: -x[1]):
        start = max(0, t - min_sec * 0.6)
        end = min(dur, start + min_sec + 4, start + max_sec)
        if end - start < min_sec:
            continue
        if all(end <= s or start >= e for s, e in picked):
            picked.append((start, end))
        if len(picked) >= n:
            break
    return sorted(picked)
