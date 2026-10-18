"""Диагностика: расшифровывает готовые клипы и показывает, что в них реально звучит (с таймкодами внутри клипа)."""
import glob
import sys

from agents.transcribe import _add_cuda_dlls, _load

_add_cuda_dlls()
model = _load("large-v3-turbo")
paths = sys.argv[1:] or sorted(glob.glob("out/*.mp4"))
for p in paths:
    segs, info = model.transcribe(p, language="ru", vad_filter=True, beam_size=1)
    segs = list(segs)
    print(f"\n=== {p}  ({info.duration:.0f} с)")
    for s in segs:
        print(f"  [{s.start:5.1f}-{s.end:5.1f}] {s.text.strip()}")
    if not segs:
        print("  (речи нет)")
