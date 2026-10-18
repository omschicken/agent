"""Поиск моментов в записи стрима: Whisper-расшифровка -> Claude выбирает рейджи/смешное/хайлайты."""
import json

import anthropic

from agents.transcribe import transcribe

PROMPT = """Ниже расшифровка записи стрима по CS2 (время в секундах от начала). Видео: «{title}», длительность {dur:.0f} с.
Найди до {n} лучших моментов для коротких вертикальных видео (15-45 секунд каждый):
 - РЕЙДЖ: стример взрывается, орёт, ругается, тильтует (ярче и эмоциональнее - лучше);
 - СМЕШНОЕ: шутки, фейлы, нелепые ситуации, смех, неожиданные реакции;
 - ХАЙЛАЙТ: клатч/эйс/красивый килл, который видно по бурной реакции стримера.
Правила:
 - момент должен быть ЗАКОНЧЕННЫМ: начало с короткой подводки (3-8 секунд до всплеска эмоций), конец - когда
   реакция/шутка отыграна, не обрывая фразу;
 - моменты не пересекаются; без пауз, разговоров ни о чём, чтения доната/чата, рекламы, новостей, обсуждения настроек;
 - не бери фрагменты, где стример читает чужую рекламу или называет промокоды сторонних сайтов;
 - границы бери по таймкодам фраз (start - начало первой нужной фразы минус подводка).
Ответь ТОЛЬКО JSON-массивом, лучшие первыми:
[{{"start": <сек>, "end": <сек>, "kind": "rage|funny|highlight", "score": <1-10>, "quote": "<самая яркая фраза>", "why": "<кратко>"}}]

РАСШИФРОВКА:
{text}"""


def _fmt(segs):
    return "\n".join(f"[{s['start']:.0f}] {s['text']}" for s in segs if s["text"])


def find_moments(path, title, duration, n, model, whisper_size="small", min_sec=12, max_sec=45):
    segs = transcribe(path, whisper_size)
    if not segs:
        return []
    text = _fmt(segs)
    # очень длинные расшифровки режем на части, чтобы влезть в контекст
    chunks, cur = [], []
    for line in text.split("\n"):
        cur.append(line)
        if sum(len(x) for x in cur) > 60000:
            chunks.append("\n".join(cur))
            cur = []
    if cur:
        chunks.append("\n".join(cur))

    client = anthropic.Anthropic()
    found = []
    for ch in chunks:
        r = client.messages.create(
            model=model, max_tokens=3000,
            messages=[{"role": "user", "content": PROMPT.format(title=title, dur=duration, n=n, text=ch)}])
        raw = "".join(b.text for b in r.content if b.type == "text").strip().strip("`").removeprefix("json").strip()
        try:
            found += json.loads(raw)
        except json.JSONDecodeError:
            print("[moments] не разобрал ответ Claude, пропускаю часть")

    out = []
    for m in sorted(found, key=lambda x: -x.get("score", 0)):
        s = max(0.0, float(m["start"]))
        e = min(duration, float(m["end"]))
        if e - s < min_sec:
            e = min(duration, s + min_sec)
        if e - s > max_sec:
            e = s + max_sec
        if e - s < min_sec or any(not (e <= a["start"] or s >= a["end"]) for a in out):
            continue
        out.append({**m, "start": round(s, 1), "end": round(e, 1)})
        if len(out) >= n:
            break
    return sorted(out, key=lambda x: x["start"])
