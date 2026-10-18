"""Поиск моментов в записи стрима.

1. audio_events: скачки громкости (рейдж/крик) и сильный смех - это КАНДИДАТЫ.
2. Whisper: расшифровка речи; для каждого кандидата берём окно текста вокруг пика.
3. Claude смотрит на кандидатов (звук + текст) и оставляет только настоящие рейджи/смешное/хайлайты,
   ставит границы: подводка -> пик -> реакция. Без звукового пика момент не рассматривается.
"""
import json
import re

import anthropic

from agents import audio_events
from agents.transcribe import transcribe

PROMPT = """Ты отбираешь моменты из записи стрима по CS2 для коротких вертикальных видео. Видео: «{title}».
Ниже КАНДИДАТЫ: места, где звук показал всплеск (резкий скачок громкости = крик/рейдж, или сильный смех).
Для каждого дан текст речи вокруг пика (время в секундах от начала стрима, метка [+N дБ] - фраза громче обычного).

Реши по каждому кандидату, настоящий ли это момент для шортса:
 - РЕЙДЖ: стример взрывается, орёт, тильтует из-за игры (умер, не попал, обокрали, проиграл раунд);
 - СМЕШНОЕ: шутка/фейл/нелепость, после которой смеются (сам стример, чат, напарники);
 - ХАЙЛАЙТ: клатч/красивый килл с бурной реакцией.
ОТКЛОНЯЙ: громкую игру без реакции человека (выстрелы, музыка, донат-алерты, реклама), ровную болтовню, чтение чата,
просто громкий голос без повода, кашель/микрофонные шумы, повтор одной фразы без развязки.

Для каждого принятого верни границы: ПОДВОДКА 6-10 с до пика (зритель понимает ситуацию), сам пик, реакция/развязка,
конец когда эмоция отыграна, не посреди фразы. Длина {min_sec}-{max_sec} с. Границы по таймкодам фраз.

Ответь ТОЛЬКО JSON-массивом, лучшие первыми (только принятые):
[{{"id": <номер кандидата>, "start": <сек>, "end": <сек>, "kind": "rage|funny|highlight", "score": <1-10>,
   "quote": "<самая яркая фраза>", "why": "<кратко: что произошло>"}}]

КАНДИДАТЫ:
{cands}"""


TRIM_PROMPT = """Это вырезка {dur:.0f} с из стрима по CS2. Зрители отметили здесь момент клипом (название клипа: «{clip}»,
просмотров: {views}). Название видео: «{title}».
Звук: {audio}
Расшифровка (время в секундах от начала вырезки, метка [+N дБ] - фраза громче обычного):
{text}

Реши, есть ли тут настоящий РЕЙДЖ (стример взрывается, орёт, тильтует), СМЕШНОЕ (шутка/фейл/нелепость, смех) или
ХАЙЛАЙТ (клатч/красивый килл с бурной реакцией). Если момент в основном ТИХИЙ (ровный разговор, обычная смерть,
ничего не происходит) - верни ok=false.
Если ok: границы {min_sec}-{max_sec} с внутри вырезки: ПОДВОДКА 4-8 с до пика (зритель понимает ситуацию), потом пик,
реакция/развязка; конец когда эмоция отыграна, не посреди фразы. Если есть голос - границы по таймкодам фраз.
Ответь ТОЛЬКО JSON:
{{"ok": true/false, "start": <сек>, "end": <сек>, "kind": "rage|funny|highlight", "score": <1-10>,
  "quote": "<самая яркая фраза или '' если речи нет>", "why": "<кратко: что произошло>"}}"""


def trim_segment(path, title, duration, meta, model, whisper_size="large-v3-turbo", min_sec=12, max_sec=45,
                 min_score=6):
    """Для вырезки по клипу зрителей: подтверждаем момент и ставим точные границы. Возвращает dict или None."""
    segs = _add_loudness(path, transcribe(path, whisper_size))
    text = _window_text(segs, 0, duration) or "  (речи нет)"
    try:
        x = audio_events._decode(path)
        ev = audio_events.loud_events(x)
    except Exception:
        ev = []
    audio = ("; ".join(f"скачок +{e['peak_db']:.0f} дБ в {e['t0']:.0f}-{e['t1']:.0f} с" for e in
                       sorted(ev, key=lambda e: -e["peak_db"])[:4]) or "заметных скачков громкости нет")
    r = anthropic.Anthropic().messages.create(
        model=model, max_tokens=1500,
        messages=[{"role": "user", "content": TRIM_PROMPT.format(
            dur=duration, clip=meta.get("clip_title", ""), views=meta.get("views", "?"), title=title,
            audio=audio, text=text, min_sec=min_sec, max_sec=max_sec)}])
    raw = "".join(b.text for b in r.content if b.type == "text").strip().strip("`").removeprefix("json").strip()
    try:
        m = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not m.get("ok") or m.get("score", 0) < min_score:
        return {"ok": False, "why": m.get("why", ""), "score": m.get("score", 0)}
    s = max(0.0, float(m["start"]))
    e = min(duration, float(m["end"]))
    if e - s < min_sec:
        e = min(duration, s + min_sec)
        s = max(0.0, e - min_sec)
    if e - s > max_sec:
        e = s + max_sec
    return {**m, "start": round(s, 1), "end": round(e, 1)}


def _tag(db):
    return f" [+{db}дБ]" if db >= 5 else ""


def _window_text(segs, t0, t1):
    return "\n".join(f"  [{s['start']:.0f}]{_tag(s.get('db', 0))} {s['text']}"
                     for s in segs if s["text"] and s["end"] >= t0 and s["start"] <= t1)


def _add_loudness(path, segs):
    from agents.curator import _loudness
    loud = _loudness(path)
    if not loud:
        return segs
    vals = sorted(m for _, m in loud)
    median = vals[len(vals) // 2]
    for s in segs:
        pts = [m for t, m in loud if s["start"] - 0.5 <= t <= s["end"] + 0.5]
        s["db"] = round(max(pts) - median) if pts else 0
    return segs


_LAUGH_RE = re.compile(r"(?i)(?:\b(?:а?х[ае]){2,}|(?:ха){2,}|(?:ах){2,}|хи-?хи|хе-?хе|ггг+|\bсмех\b|ржу|угараю)")


def _text_laughs(segs):
    """Смех по тексту: Whisper пишет «ха-ха-ха», «ахахах», «хихи». Это дополнение к звуковому классификатору."""
    out = []
    for s in segs:
        if _LAUGH_RE.search(s["text"]):
            out.append({"kind": "laugh", "t0": s["start"], "t1": s["end"], "p": 0.6, "score": 10.0})
    return out


def _merge(events, gap=8.0):
    """Склеиваем близкие события (скачок громкости + смех рядом = один сильный кандидат)."""
    evs = sorted(events, key=lambda e: e["t0"])
    out = []
    for e in evs:
        if out and e["t0"] <= out[-1]["t1"] + gap:
            o = out[-1]
            o["t1"] = max(o["t1"], e["t1"])
            o["kinds"].add(e["kind"])
            o["score"] += e["score"] * (1.5 if e["kind"] != next(iter(o["kinds"] - {e["kind"]}), e["kind"]) else 1)
        else:
            out.append({"t0": e["t0"], "t1": e["t1"], "kinds": {e["kind"]}, "score": e["score"]})
    return out


def find_moments(path, title, duration, n, model, whisper_size="large-v3-turbo", min_sec=15, max_sec=45,
                 pre=30, post=20, max_cands=14, min_loud_db=12.0, min_laugh=0.2, min_score=7):
    """Берём только сильные звуковые пики: скачок громкости >= min_loud_db или смех >= min_laugh;
    принимаем только моменты, которым Claude дал оценку >= min_score."""
    segs = _add_loudness(path, transcribe(path, whisper_size))
    events = [e for e in audio_events.detect(path) + _text_laughs(segs)
              if (e["kind"] == "loud" and e.get("peak_db", 0) >= min_loud_db)
              or (e["kind"] == "laugh" and e.get("p", 0) >= min_laugh)]
    cands = sorted(_merge(events), key=lambda c: -c["score"])[:max_cands]
    print(f"[moments] аудио-кандидатов: {len(cands)} (громкость: {sum(e['kind']=='loud' for e in events)}, "
          f"смех: {sum(e['kind']=='laugh' for e in events)})")
    if not cands:
        return []
    cands.sort(key=lambda c: c["t0"])
    blocks = []
    for i, c in enumerate(cands):
        kinds = "+".join(sorted("смех" if k == "laugh" else "скачок громкости" for k in c["kinds"]))
        blocks.append(f"### Кандидат {i}: {kinds}, пик {c['t0']:.0f}-{c['t1']:.0f} с\n"
                      + (_window_text(segs, c["t0"] - pre, c["t1"] + post) or "  (речи нет)"))

    r = anthropic.Anthropic().messages.create(
        model=model, max_tokens=4000,
        messages=[{"role": "user", "content": PROMPT.format(
            title=title, min_sec=min_sec, max_sec=max_sec, cands="\n\n".join(blocks))}])
    raw = "".join(b.text for b in r.content if b.type == "text").strip().strip("`").removeprefix("json").strip()
    try:
        picked = json.loads(raw)
    except json.JSONDecodeError:
        print("[moments] не разобрал ответ Claude")
        return []

    out = []
    for m in sorted(picked, key=lambda x: -x.get("score", 0)):
        if m.get("score", 0) < min_score:
            continue
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
