"""Проверка ключа и баланса Anthropic API одним крошечным запросом."""
import os

import anthropic

try:
    r = anthropic.Anthropic().messages.create(model="claude-sonnet-5-5", max_tokens=10,
                                              messages=[{"role": "user", "content": "ок"}])
    print("API РАБОТАЕТ:", "".join(b.text for b in r.content if b.type == "text"))
except Exception as e:
    print("API НЕ РАБОТАЕТ:", str(e)[:200])
