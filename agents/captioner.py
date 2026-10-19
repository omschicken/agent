"""Подписчик: Claude смотрит кадры клипа и сочиняет короткую подпись, которая вшивается сверху в видео.

Стиль (одобрен заказчиком): коротко, разговорно, «кто + что случилось»:
«нереальный хайлайт от tried’а», «скай попался с нейросетью».
"""
import base64
import json
import os
import tempfile

import anthropic

from agents.judge import _frames
from agents.transcribe import transcribe

PROMPT = """Ты монтажёр канала с моментами из CS2. Перед тобой {n} кадров клипа по порядку и данные о нём.
Придумай ПОДПИСЬ, которую вставят текстом СВЕРХУ в видео (зритель читает её в первые секунды).

Стиль подписи: очень коротко (до {max_chars} символов), разговорно, как написал бы друг, который скинул клип: «кто + что
случилось». Строчные буквы (имена и ники как в данных), без капса, без точки в конце, без «смотрите / шок / вы не
поверите», максимум один эмодзи или без. Для хайлайта - про сам игровой момент (клатч, эйс, неожиданный килл),
для смешного - что произошло, для рейджа - из-за чего сорвался.
Опирайся на кадры (киллфид, счёт, табло, что делает игрок), расшифровку и данные. НЕ выдумывай имён, ников и событий,
которых не видно и не названо; если не уверен, кто герой, называй по стримеру из источника.

{approved}
ДАННЫЕ О КЛИПЕ:
Источник/название: {note}
Расшифровка клипа: {text}

Ответь ТОЛЬКО JSON: {{"caption": "<подпись>"}}"""


def _img(path):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(open(path, "rb").read()).decode()}}


def _approved_blocks():
    """Одобренные подписи с кадрами (examples/approved.json + appr_i_k.jpg)."""
    p = os.path.join("examples", "approved.json")
    if not os.path.exists(p):
        return []
    blocks = [{"type": "text", "text": "ОБРАЗЦЫ ОДОБРЕННЫХ ПОДПИСЕЙ (повтори стиль и степень краткости, не копируй слова):"}]
    for i, x in enumerate(json.load(open(p, encoding="utf-8"))):
        blocks.append({"type": "text", "text": f"Образец {i + 1}: {x['data']}\nПодпись: «{x['caption']}»"})
        for k in (0, 1):
            f = os.path.join("examples", f"appr_{i}_{k}.jpg")
            if os.path.exists(f):
                blocks.append(_img(f))
    blocks.append({"type": "text", "text": "КОНЕЦ ОБРАЗЦОВ. Теперь твой клип:"})
    return blocks


def caption(src, start, end, note, model, whisper_size="large-v3-turbo", covers=None, max_chars=40):
    """Подпись для клипа [start, end] видео src или None, если не получилось."""
    try:
        segs = transcribe(src, whisper_size)
        text = " ".join(s["text"] for s in segs if s["end"] >= start and s["start"] <= end).strip()[:700]
    except Exception:
        text = ""
    with tempfile.TemporaryDirectory() as tmp:
        frames = [_img(f) for f in _frames(src, start, end, 6, tmp, covers=covers)]
    if not frames:
        return None
    prompt = PROMPT.format(n=len(frames), max_chars=max_chars, approved="", note=note[:600], text=text or "(речи нет)")
    try:
        r = anthropic.Anthropic().messages.create(
            model=model, max_tokens=800,
            messages=[{"role": "user", "content": _approved_blocks() + frames + [{"type": "text", "text": prompt}]}])
        raw = "".join(b.text for b in r.content if b.type == "text").strip().strip("`").removeprefix("json").strip()
        cap = json.loads(raw).get("caption", "").strip().strip("«»\"")
    except Exception as e:
        print(f"[caption] не получилось ({str(e)[:100]})")
        return None
    return cap[: max_chars + 8] if cap else None
