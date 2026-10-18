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
    credit = f"\nИсточник: {note}" if note else ""
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


def _claude_copy(filename, note, brand, platforms, model):
    import anthropic

    client = anthropic.Anthropic()
    prompt = f"""Ты SMM-редактор канала про CS2. Клип: «{note or filename}».
Верни JSON вида {{"<платформа>": {{"title": "...", "description": "...", "hashtags": ["..."]}}}}
для платформ: {platforms}. Правила: заголовок до 70 символов, цепляющий, без ложного кликбейта;
в описании источник клипа (если он указан в описании клипа), упоминание сайта {brand['site_name']}
и промокода {brand['promo_code']}, а также строка «{brand['disclaimer']}». Только JSON."""
    r = client.messages.create(
        model=model, max_tokens=1200, messages=[{"role": "user", "content": prompt}]
    )
    text = r.content[0].text.strip().strip("`").removeprefix("json").strip()
    return json.loads(text)


def write_copy(filename, note, brand, platforms, model, provider="auto"):
    use_claude = provider == "claude" or (provider == "auto" and os.environ.get("ANTHROPIC_API_KEY"))
    if use_claude:
        try:
            return _claude_copy(filename, note, brand, platforms, model)
        except Exception as e:  # нет денег/сети/битый JSON - не роняем пайплайн
            print(f"[copywriter] Claude недоступен ({e}), использую шаблоны")
    return _template_copy(filename, note, brand, platforms)
