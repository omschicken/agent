"""Claude пишет заголовок/описание/хэштеги под каждую платформу."""
import json

import anthropic

client = anthropic.Anthropic()


def write_copy(filename, note, brand, platforms, model):
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
