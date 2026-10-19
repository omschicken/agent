"""Собирает пример клипа вручную (без API): исходник, интервал, закрываемая реклама. Используется баннер из config.yaml.

python make_example.py <исходник.mp4> <начало> <конец> <выход.mp4> [x,y,w,h ...]   (прямоугольники рекламы в долях кадра)
"""
import sys

import yaml

from agents import editor

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
src, start, end, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
covers = [tuple(float(v) for v in a.split(",")) for a in sys.argv[5:]]
editor.render(src, start, end, out, cfg["brand"], covers=covers)
print("готово:", out)
