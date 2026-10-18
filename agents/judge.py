"""Судья: Claude смотрит кадры видео/клипа и решает, годится ли оно для нашего канала.

Отсекает: лица/вебкамеру, чужие сайты кейсов, розыгрыши и рекламу сторонних проектов,
разговоры/настройки без игрового момента, скучные открытия кейсов (оставляем смешное или очень редкий дроп).
"""
import base64
import json
import os
import subprocess
import tempfile

import anthropic

PROMPT = """Ты отбираешь материал для коротких вертикальных видео канала про CS2, который рекламирует СВОЙ сайт
с кейсами. Перед тобой {n} кадров, равномерно взятых из видео/клипа (контекст: «{ctx}»).
Определи по кадрам и верни ТОЛЬКО JSON:
{{
 "frames_with_face": <сколько кадров, где виден человек: лицо, вебкамера, рука с камерой, аватарка-фото>,
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


def _frames(path, start, end, n, tmp):
    out = []
    for i in range(n):
        t = start + (end - start) * (i + 0.5) / n
        f = os.path.join(tmp, f"f{i}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path,
             "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "5", f],
            check=False,
        )
        if os.path.exists(f):
            out.append(f)
    return out


def _duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def look(path, ctx, model, n=8, start=0.0, end=None):
    """Возвращает dict-вердикт от Claude или None, если судья недоступен."""
    end = end or _duration(path)
    with tempfile.TemporaryDirectory() as tmp:
        files = _frames(path, start, end, n, tmp)
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


def verdict(v, rules):
    """(ok, причина) по правилам из config.yaml -> judge."""
    if v is None:
        return True, "судья недоступен"
    n = max(v.get("_n", 1), 1)
    if v.get("frames_with_face", 0) / n > rules.get("max_face_ratio", 0.15):
        return False, "лица/вебкамера"
    if rules.get("require_cs2", True) and not v.get("is_cs2_gameplay"):
        return False, "не игровой процесс CS2"
    if v.get("third_party_site"):
        return False, "сторонний сайт/чужая реклама"
    if v.get("giveaway_or_promo"):
        return False, "розыгрыш/промо"
    if v.get("content_type") == "talking_or_settings":
        return False, "разговор/настройки"
    if v.get("content_type") == "case_drop" and not v.get("rare_drop") and v.get("score", 0) < rules.get("case_min_score", 8):
        return False, "скучное открытие кейса"
    if v.get("score", 0) < rules.get("min_score", 6):
        return False, f"слабый момент ({v.get('score')}): {v.get('reason', '')}"
    return True, v.get("reason", "")
