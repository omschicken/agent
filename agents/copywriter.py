"""Тексты под платформы: Claude (если есть ключ) или шаблоны (бесплатный запасной вариант)."""
import json
import os
import random

TITLES = [
    "Это надо видеть: {topic}",
    "{topic} — вот это момент 🔥",
    "Не ожидал такого: {topic}",
    "CS2: {topic}",
    "Лучший момент дня: {topic}",
    "Ты не поверишь, что случилось: {topic}",
]
HASHTAGS = ["cs2", "csgo", "counterstrike", "cs2highlights", "кс2", "хайлайты", "cases", "gaming"]


def _template_copy(filename, note, brand, platforms):
    topic = (note.splitlines()[0] if note else filename.replace("_", " ")).strip()[:50]
    rest = "\n".join(note.splitlines()[1:]).strip()  # строки после названия (источник/автор)
    credit = f"\n{rest}" if rest else ""
    out = {}
    for p in platforms:
        tags = random.sample(HASHTAGS, 5)
        out[p] = {
            "title": random.choice(TITLES).format(topic=topic)[:70],
            "description": (
                f"Открывай кейсы на {brand['site_name']}, промокод {brand['promo_code']}.\n"
                f"{brand['disclaimer']}{credit}"
            ),
            "hashtags": tags,
        }
    return out


def _approved_block():
    """Подписи, которые одобрил заказчик (examples/approved.json), как образец стиля."""
    p = os.path.join("examples", "approved.json")
    if not os.path.exists(p):
        return ""
    items = json.load(open(p, encoding="utf-8"))
    lines = [f"- данные: {x['data']}\n  подпись: «{x['caption']}»" for x in items]
    return "ОБРАЗЦЫ ОДОБРЕННЫХ ПОДПИСЕЙ (повтори стиль, не копируй слова):\n" + "\n".join(lines) + "\n"


def _claude_copy(filename, note, brand, platforms, model):
    import anthropic

    client = anthropic.Anthropic()
    prompt = f"""Ты SMM-редактор канала про CS2. Клип: «{note or filename}».
{_approved_block()}
Верни JSON вида {{"<платформа>": {{"title": "...", "description": "...", "hashtags": ["..."]}}}}
для платформ: {platforms}.
СТИЛЬ заголовка (title) - КОРОТКАЯ разговорная подпись, как написал бы друг, который скинул клип: «кто + что случилось»,
до 45 символов, строчными буквами (имена и ники как в источнике), без капса, без «смотрите/вы не поверите/шок»,
максимум один эмодзи или без. Примеры того, что нужно: «нереальный хайлайт от tried’а», «скай попался с нейросетью».
Опирайся ТОЛЬКО на факты из данных клипа (ник стримера из источника, название зрительского клипа, цитата, что
произошло). Не придумывай имён, ников и событий, которых нет в данных; если непонятно, кто герой, называй
по стримеру из источника. Для хайлайта - про сам игровой момент, для смешного - про то, что произошло, для рейджа - про
причину срыва.
Описание (description): первая строка - та же короткая подпись, дальше источник клипа (если он указан в описании клипа),
упоминание сайта {brand['site_name']}
и промокода {brand['promo_code']}, а также строка «{brand['disclaimer']}». Про сайт и промокод пиши только
факты (название и сам код): НЕ обещай бонусы, скидки, выигрыши, заработок, «гарантированный дроп» и не
выдумывай условия, которых тебе не дали. Только JSON."""
    r = client.messages.create(
        model=model, max_tokens=4000, messages=[{"role": "user", "content": prompt}]
    )
    text = "".join(b.text for b in r.content if b.type == "text")
    text = text.strip().strip("`").removeprefix("json").strip()
    return json.loads(text)


def write_copy(filename, note, brand, platforms, model, provider="auto", caption=None):
    """caption - подпись, вшитая в видео (её придумал агент по кадрам): идёт заголовком и первой строкой описания."""
    use_claude = provider == "claude" or (provider == "auto" and os.environ.get("ANTHROPIC_API_KEY"))
    copy = None
    if use_claude:
        try:
            copy = _claude_copy(filename, note, brand, platforms, model)
        except Exception as e:  # нет денег/сети/битый JSON - не роняем пайплайн
            print(f"[copywriter] Claude недоступен ({e}), использую шаблоны")
    if copy is None:
        copy = _template_copy(filename, note, brand, platforms)
    if caption:
        for p in platforms:
            if p in copy:
                copy[p]["title"] = caption
                copy[p]["description"] = caption + "\n\n" + copy[p].get("description", "")
    return copy
