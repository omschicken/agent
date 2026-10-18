"""Тестовый прогон: небольшая выборка, ролики пониже качеством, без публикации."""
import sys

import yaml

from agents import scout

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
s = cfg["scout"]
s["max_new_videos"] = int(sys.argv[1]) if len(sys.argv) > 1 else 8
s["per_query"] = 3
s["max_height"] = 720
s["min_duration"] = 300      # записи стримов, не шортсы
s["max_duration"] = 1800
print("downloaded", scout.scout(cfg))
