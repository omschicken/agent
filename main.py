"""Оркестратор: (разведчик) -> судья источника -> куратор -> судья клипа -> монтаж -> копирайт -> публикация."""
import glob
import json
import os
import shutil
import sys
import time

import yaml

from agents import copywriter, curator, editor, judge, publisher

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"  # по умолчанию ничего не постим
JUDGE = cfg.get("judge", {}).get("enabled") and os.environ.get("ANTHROPIC_API_KEY")
if cfg.get("judge", {}).get("enabled") and not JUDGE:
    print("[judge] нет ANTHROPIC_API_KEY - проверка по кадрам отключена!")

if "--scout" in sys.argv:  # сначала сам находит и скачивает видео
    from agents import scout
    scout.scout(cfg)

os.makedirs("rejected", exist_ok=True)


def reject(src, why):
    """Не удаляем, а переносим в rejected/ - чтобы можно было посмотреть, прав ли судья."""
    print(f"[judge] ОТКЛОНЕНО {os.path.basename(src)}: {why}")
    for ext in (".mp4", ".txt"):
        try:
            shutil.move(src[:-4] + ext, os.path.join("rejected", os.path.basename(src)[:-4] + ext))
        except OSError:
            pass


for src in glob.glob("inbox/*.mp4"):
    name = os.path.splitext(os.path.basename(src))[0]
    note_file = src[:-4] + ".txt"  # необязательно: описание момента + источник/credit
    note = open(note_file, encoding="utf-8").read().strip() if os.path.exists(note_file) else ""
    title = note.splitlines()[0] if note else name
    crop = None

    if JUDGE:  # весь ролик: лица, чужие сайты, розыгрыши, разговоры; вебкамеру срезаем
        v = judge.look(src, title, cfg["model"], n=cfg["judge"].get("source_frames", 8))
        ok, why = judge.verdict(v, cfg["judge"], source=True)
        if not ok:
            reject(src, why)
            continue
        crop = None if cfg["judge"].get("allow_webcam") else judge.crop_for(v)
        if crop:
            print(f"[judge] {name}: срезаю вебкамеру, оставляю область {tuple(round(c, 2) for c in crop)}")

    notes = {}  # (start, end) -> описание момента для копирайтера
    if cfg["clip"].get("mode") == "transcript" and os.environ.get("ANTHROPIC_API_KEY"):
        # запись стрима: Whisper + Claude находят рейджи/смешное/хайлайты по смыслу
        from agents import moments
        dur = judge._duration(src)
        print(f"[moments] {name}: расшифровываю {dur/60:.0f} мин речи...")
        found = moments.find_moments(
            src, title, dur, cfg["clip"]["per_source"] * 2, cfg["model"],
            cfg["clip"].get("whisper_model", "small"),
            cfg["clip"].get("moment_min_sec", 15), cfg["clip"].get("moment_max_sec", 45))
        spans = [(m["start"], m["end"]) for m in found]
        for m in found:
            notes[(m["start"], m["end"])] = f"{m.get('kind')}: «{m.get('quote')}» ({m.get('why')})"
            print(f"[moments] {m['start']:.0f}-{m['end']:.0f}с {m.get('kind')} {m.get('score')}/10 «{m.get('quote')}»")
    else:
        spans = curator.find_highlights(
            src, cfg["clip"]["min_sec"], cfg["clip"]["max_sec"],
            cfg["clip"]["per_source"] * 3 if JUDGE else cfg["clip"]["per_source"],
        )
    made = 0
    for s, e in spans:
        if made >= cfg["clip"]["per_source"]:
            break
        if JUDGE:  # каждый клип отдельно: законченный цепляющий момент без лиц?
            v = judge.look(src, title, cfg["model"], n=cfg["judge"].get("clip_frames", 4),
                           start=s, end=e, crop=crop)
            ok, why = judge.verdict(v, cfg["judge"])
            if not ok:
                print(f"[judge] клип {s:.0f}-{e:.0f}с отклонён: {why}")
                continue
        made += 1
        out = f"out/{name}_{made}.mp4"
        editor.render(src, s, e, out, cfg["brand"], crop=crop)
        moment_note = note + (f"\nМомент {notes[(s, e)]}" if (s, e) in notes else "")
        copy = copywriter.write_copy(name, moment_note, cfg["brand"], cfg["platforms"], cfg["model"],
                                     cfg.get("copy_provider", "auto"))
        with open(out[:-4] + ".json", "w", encoding="utf-8") as f:
            json.dump(copy, f, ensure_ascii=False, indent=2)
        print("ready:", out)
        if not DRY_RUN:
            for p in cfg["platforms"]:
                publisher.PUBLISHERS[p](out, copy[p])
