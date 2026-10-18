"""Судья: Claude смотрит кадры видео/клипа и решает, годится ли оно для нашего канала.

Отсекает: лица/вебкамеру, чужие сайты кейсов, розыгрыши и рекламу сторонних проектов,
разговоры/настройки без игрового момента, скучные открытия кейсов (оставляем смешное или очень редкий дроп).
"""
import base64
import json
import os
from agents.proc import run
import tempfile

import anthropic

PROMPT = """Ты отбираешь материал для коротких вертикальных видео канала про CS2, который рекламирует СВОЙ сайт
с кейсами. Перед тобой {n} кадров, равномерно взятых из видео/клипа (контекст: «{ctx}»).
Определи по кадрам и верни ТОЛЬКО JSON:
{{
 "frames_with_face": <сколько кадров, где виден человек: лицо, вебкамера, рука с камерой, аватарка-фото>,
 "webcam_box": <null, если нет вебкамеры. Если стример показан в небольшом окошке-оверлее, которое стоит на ОДНОМ
                месте во всех кадрах (обычно в углу): {{"x": 0-1, "y": 0-1, "w": 0-1, "h": 0-1}} - его рамка в долях
                кадра (x,y - левый верхний угол). Рамку делай с запасом на пару процентов>,
 "face_outside_webcam": <true, если лица/люди видны ГДЕ-ТО ЕЩЁ, кроме этого оверлея: на весь экран, IRL-кадры,
                         несколько окон с камерами>,
 "is_cs2_gameplay": <true, если это игровой процесс/интерфейс именно CS2 или CS:GO>,
 "third_party_site": <true, если открытие/дроп показан на сторонней сайте-кейсах (не в клиенте CS2/Steam-инвентаре),
                      или видны логотипы/баннеры/промокоды чужих сайтов>,
 "giveaway_or_promo": <true, если розыгрыш, giveaway, конкурс, реклама чужого проекта>,
 "content_type": "clutch_ace" | "funny_fail" | "case_drop" | "lifehack_tutorial" | "talking_or_settings" | "other",
 "rare_drop": <true, если виден редкий дроп: нож, перчатки, золотой/красный предмет>,
 "score": <0-10: насколько это цепляющий законченный момент для шортса. Открытие кейса со скучным дропом - 0-3.
          Меню настроек, разговор, статичная картинка - 0-2.>,
 "reason": "<одна короткая фраза>"
}}"""


def crop_filter(crop):
    """crop = (x, y, w, h) в долях кадра -> фильтр ffmpeg или ''."""
    if not crop:
        return ""
    x, y, w, h = crop
    return f"crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f},"


def crop_for(v):
    """Как срезать вебкамеру: возвращает (x, y, w, h) оставляемой области или None (срезать нельзя/не нужно)."""
    box = (v or {}).get("webcam_box")
    if not box or v.get("face_outside_webcam"):
        return None
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0.4 and (x + w / 2) < 0.5:   # камера слева -> срезаем левую полосу
        return (min(x + w, 0.6), 0.0, 1 - min(x + w, 0.6), 1.0)
    if w <= 0.4:                         # камера справа -> срезаем правую полосу
        return (0.0, 0.0, max(x, 0.4), 1.0)
    if h <= 0.35 and (y + h / 2) < 0.5:  # сверху
        return (0.0, min(y + h, 0.65), 1.0, 1 - min(y + h, 0.65))
    if h <= 0.35:                        # снизу
        return (0.0, 0.0, 1.0, max(y, 0.35))
    return None


def _frames(path, start, end, n, tmp, crop=None):
    out = []
    for i in range(n):
        t = start + (end - start) * (i + 0.5) / n
        f = os.path.join(tmp, f"f{i}.jpg")
        run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path,
             "-frames:v", "1", "-vf", crop_filter(crop) + "scale=640:-2", "-q:v", "5", f],
            check=False,
        )
        if os.path.exists(f):
            out.append(f)
    return out


def _duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def look(path, ctx, model, n=8, start=0.0, end=None, crop=None):
    """Возвращает dict-вердикт от Claude или None, если судья недоступен. crop - область без вебкамеры."""
    end = end or _duration(path)
    with tempfile.TemporaryDirectory() as tmp:
        files = _frames(path, start, end, n, tmp, crop)
        if not files:
            return None
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                "data": base64.b64encode(open(f, "rb").read()).decode()}}
                   for f in files]
        content.append({"type": "text", "text": PROMPT.format(n=len(files), ctx=ctx[:200])})
        try:
            r = anthropic.Anthropic().messages.create(
                model=model, max_tokens=1000, messages=[{"role": "user", "content": content}])
            text = "".join(b.text for b in r.content if b.type == "text").strip().strip("`").removeprefix("json").strip()
            v = json.loads(text)
            v["_n"] = len(files)
            return v
        except Exception as e:
            print(f"[judge] недоступен ({e})")
            return None


def verdict(v, rules, source=False):
    """(ok, причина) по правилам из config.yaml -> judge.
    source=True: проверка всего видео - оценку «цепляющести» не применяем (она для отдельных клипов)."""
    if v is None:
        return True, "судья недоступен"
    n = max(v.get("_n", 1), 1)
    if rules.get("curated"):  # источник - белый список авторов, моменты уже отобраны ими: только жёсткие проверки
        if rules.get("require_cs2", True) and not v.get("is_cs2_gameplay"):
            return False, "не игровой процесс CS2"
        if v.get("third_party_site"):
            return False, "сторонний сайт/чужая реклама"
        if v.get("giveaway_or_promo"):
            return False, "розыгрыш/промо"
        if v.get("content_type") == "talking_or_settings":
            return False, "разговор/настройки"
        return True, v.get("reason", "")
    if rules.get("allow_webcam") and v.get("face_outside_webcam"):
        return False, "лицо/человек вне оверлея-вебкамеры (во весь экран, IRL)"
    if v.get("frames_with_face", 0) / n > rules.get("max_face_ratio", 0.15) and not rules.get("allow_webcam"):
        if v.get("webcam_box") and not v.get("face_outside_webcam"):
            if crop_for(v) is None:
                return False, "вебкамеру нельзя срезать без потери геймплея"
        else:
            return False, "лица в кадре (не оверлей-вебкамера)"
    if rules.get("require_cs2", True) and not v.get("is_cs2_gameplay"):
        return False, "не игровой процесс CS2"
    if v.get("third_party_site"):
        return False, "сторонний сайт/чужая реклама"
    if v.get("giveaway_or_promo"):
        return False, "розыгрыш/промо"
    if v.get("content_type") == "talking_or_settings":
        return False, "разговор/настройки"
    if source:
        return True, v.get("reason", "")
    if v.get("content_type") == "case_drop" and not v.get("rare_drop") and v.get("score", 0) < rules.get("case_min_score", 8):
        return False, "скучное открытие кейса"
    if v.get("score", 0) < rules.get("min_score", 6):
        return False, f"слабый момент ({v.get('score')}): {v.get('reason', '')}"
    return True, v.get("reason", "")
