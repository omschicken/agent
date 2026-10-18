"""Оркестратор: inbox/*.mp4 -> куратор -> монтаж -> копирайт -> публикация."""
import glob
import json
import os

import yaml

from agents import copywriter, curator, editor, publisher

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"  # по умолчанию ничего не постим

for src in glob.glob("inbox/*.mp4"):
    name = os.path.splitext(os.path.basename(src))[0]
    note_file = src[:-4] + ".txt"  # необязательно: описание момента + источник/credit
    note = open(note_file, encoding="utf-8").read().strip() if os.path.exists(note_file) else ""
    spans = curator.find_highlights(
        src, cfg["clip"]["min_sec"], cfg["clip"]["max_sec"], cfg["clip"]["per_source"]
    )
    for i, (s, e) in enumerate(spans, 1):
        out = f"out/{name}_{i}.mp4"
        editor.render(src, s, e, out, cfg["brand"])
        copy = copywriter.write_copy(name, note, cfg["brand"], cfg["platforms"], cfg["model"])
        with open(out[:-4] + ".json", "w", encoding="utf-8") as f:
            json.dump(copy, f, ensure_ascii=False, indent=2)
        print("ready:", out)
        if not DRY_RUN:
            for p in cfg["platforms"]:
                publisher.PUBLISHERS[p](out, copy[p])
