"""Судья: Claude смотрит кадры видео/клипа и решает, годится ли оно для нашего канала.

Отсекает: чужие сайты кейсов во весь экран, розыгрыши, разговоры/настройки, скучные открытия кейсов.
Чужие рекламные оверлеи (ставки, скины, кейсы, промокоды) судья находит как прямоугольники (ad_boxes) -
редактор закрывает их размытием, а повторная проверка идёт уже по закрытому кадру.
"""
import base64
import json
import os
import tempfile

import anthropic

from agents.proc import run

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
 "ad_boxes": <список ПРЯМОУГОЛЬНИКОВ с чужой рекламой, ЧИТАЕМОЙ на кадрах: оверлеи-баннеры, плашки с промокодами,
              «рефка под стримом», логотипы и надписи сайтов ставок/букмекеров/казино/скинов/кейсов/апгрейдеров
              (BetBoom, Fonbet, Winline, LIS-SKINS, Upgrader, Кейсер и т.п.). Каждый: {{"x": 0-1, "y": 0-1, "w": 0-1, "h": 0-1}}
              в долях кадра (x,y - левый верхний угол), с запасом около 2% со всех сторон. Объедини соседние
              элементы в один прямоугольник. Если такой рекламы на кадрах нет - []. Faceit, HLTV, Steam, Twitch, YouTube,
              логотипы турниров и команд, донат-алерты - НЕ реклама>,
 "third_party_site": <true ТОЛЬКО если интерфейс стороннего сайта кейсов/скинов/ставок/казино занимает основную часть
                      экрана (сам сайт - это содержимое кадра, и закрыть его прямоугольником нельзя). Если это только
                      баннеры/оверлеи поверх игры - false, а прямоугольники положи в ad_boxes>,
 "giveaway_or_promo": <true ТОЛЬКО если явно идёт розыгрыш/giveaway/конкурс на призы. Баннеры спонсоров - не розыгрыш>,
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


def prefix_graph(covers, crop):
    """filter_complex: закрываем рекламные прямоугольники размытием, затем кадрируем. Выход - метка [pre]."""
    g = "[0:v]null[s0];"
    for i, (x, y, w, h) in enumerate(covers or []):
        g += (f"[s{i}]split[m{i}][n{i}];"
              f"[n{i}]crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f},gblur=sigma=34:steps=3[b{i}];"
              f"[m{i}][b{i}]overlay=W*{x:.4f}:H*{y:.4f}[s{i + 1}];")
    g += f"[s{len(covers or [])}]{crop_filter(crop)}null[pre];"
    return g


def covers_for(v, max_boxes=6):
    """Прямоугольники рекламы из вердикта -> список (x, y, w, h) в границах кадра."""
    out = []
    for b in ((v or {}).get("ad_boxes") or [])[:max_boxes]:
        try:
            x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError):
            continue
        x, y = max(0.0, x), max(0.0, y)
        w, h = min(w, 1 - x), min(h, 1 - y)
        if w > 0.01 and h > 0.01:
            out.append((x, y, w, h))
    return out


def cover_area(covers):
    return sum(w * h for _, _, w, h in covers)


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


def _frames(path, start, end, n, tmp, crop=None, covers=None):
    out = []
    graph = prefix_graph(covers, crop) + "[pre]scale=640:-2[o]"
    for i in range(n):
        t = start + (end - start) * (i + 0.5) / n
        f = os.path.join(tmp, f"f{i}.jpg")
        run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path,
             "-filter_complex", graph, "-map", "[o]", "-frames:v", "1", "-q:v", "5", f],
            check=False,
        )
        if os.path.exists(f):
            out.append(f)
    return out


def _duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True)
    return float(r.stdout.strip())


def look(path, ctx, model, n=8, start=0.0, end=None, crop=None, covers=None):
    """Возвращает dict-вердикт от Claude или None, если судья недоступен.
    crop - область без вебкамеры, covers - уже закрываемые рекламные прямоугольники."""
    end = end or _duration(path)
    with tempfile.TemporaryDirectory() as tmp:
        files = _frames(path, start, end, n, tmp, crop, covers)
        if not files:
            return None
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                "data": base64.b64encode(open(f, "rb").read()).decode()}}
                   for f in files]
        content.append({"type": "text", "text": PROMPT.format(n=len(files), ctx=ctx[:200])})
        for attempt in range(2):
            try:
                r = anthropic.Anthropic().messages.create(
                    model=model, max_tokens=2500, messages=[{"role": "user", "content": content}])
                text = "".join(b.text for b in r.content if b.type == "text").strip().strip("`").removeprefix("json").strip()
                v = json.loads(text)
                v["_n"] = len(files)
                return v
            except Exception as e:
                if attempt == 1:
                    print(f"[judge] недоступен ({str(e)[:100]})")
        return None


def verdict(v, rules, source=False, covered=False):
    """(ok, причина) по правилам из config.yaml -> judge.
    source=True: проверка всего видео - оценку «цепляющести» не применяем (она для отдельных клипов).
    covered=True: кадры уже с закрытой рекламой - если реклама всё ещё читается (ad_boxes не пуст), отклоняем."""
    if v is None:
        return True, "судья недоступен"
    n = max(v.get("_n", 1), 1)

    ads = covers_for(v)
    if covered and ads:
        return False, "чужая реклама осталась в кадре после закрытия"
    if not covered and cover_area(ads) > rules.get("max_cover_area", 0.35):
        return False, f"чужая реклама занимает слишком большую часть кадра ({cover_area(ads):.0%})"

    if rules.get("curated"):  # источник - белый список авторов, моменты уже отобраны: только жёсткие проверки
        if v.get("third_party_site"):
            return False, "интерфейс стороннего сайта кейсов/ставок во весь экран"
        if v.get("giveaway_or_promo"):
            return False, "розыгрыш"
        if rules.get("skip_content_checks"):  # вырезка по клипу зрителей: момент уже подтверждён по кадрам и звуку
            return True, v.get("reason", "")
        if rules.get("require_cs2", True) and not v.get("is_cs2_gameplay"):
            return False, "не игровой процесс CS2"
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
        return False, "интерфейс стороннего сайта кейсов/ставок во весь экран"
    if v.get("giveaway_or_promo"):
        return False, "розыгрыш"
    if v.get("content_type") == "talking_or_settings":
        return False, "разговор/настройки"
    if source:
        return True, v.get("reason", "")
    if v.get("content_type") == "case_drop" and not v.get("rare_drop") and v.get("score", 0) < rules.get("case_min_score", 8):
        return False, "скучное открытие кейса"
    if v.get("score", 0) < rules.get("min_score", 6):
        return False, f"слабый момент ({v.get('score')}): {v.get('reason', '')}"
    return True, v.get("reason", "")
