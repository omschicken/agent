"""Готовая картинка баннера (GPT) -> banner/card.png: карточка со скруглёнными углами на прозрачном фоне.

python banner/prep_card.py <баннер.png>
Печатает рамку карточки и радиус скругления; кладёт debug-картинку banner/stills/card_debug.png с размеченными зонами.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
im = Image.open(sys.argv[1]).convert("RGB")
a = np.asarray(im).astype(np.float32)
lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
bright = lum > 95

# рамка карточки: строки/столбцы, где много светлых пикселей
cols = np.where(bright.mean(axis=0) > 0.30)[0]
rows = np.where(bright.mean(axis=1) > 0.30)[0]
x0, x1, y0, y1 = int(cols[0]), int(cols[-1]) + 1, int(rows[0]), int(rows[-1]) + 1

# радиус скругления: смещение первого светлого пикселя в самой верхней строке карточки
top = np.where(bright[y0 + 1, x0:x1])[0]
radius = int(top[0]) + 2 if len(top) else 56
radius = max(30, min(radius, 90))

card = im.crop((x0, y0, x1, y1))
w, h = card.size
mask = Image.new("L", (w * 2, h * 2), 0)
ImageDraw.Draw(mask).rounded_rectangle((1, 1, w * 2 - 2, h * 2 - 2), radius=radius * 2, fill=255)
mask = mask.resize((w, h), Image.LANCZOS)
out = card.convert("RGBA")
out.putalpha(mask)
out.save(os.path.join(HERE, "card.png"))
json.dump({"bbox": [x0, y0, x1, y1], "size": [w, h], "radius": radius}, open(os.path.join(HERE, "card.json"), "w"))
print(f"карточка {w}x{h}, рамка {x0},{y0}-{x1},{y1}, радиус {radius}")

# отладочная картинка: сетка по 100 px для разметки зон
dbg = out.convert("RGB").copy()
d = ImageDraw.Draw(dbg)
for gx in range(0, w, 100):
    d.line((gx, 0, gx, h), fill=(255, 0, 0), width=1)
    d.text((gx + 3, 3), str(gx), fill=(255, 0, 0))
for gy in range(0, h, 100):
    d.line((0, gy, w, gy), fill=(0, 120, 255), width=1)
    d.text((3, gy + 3), str(gy), fill=(0, 120, 255))
os.makedirs(os.path.join(HERE, "stills"), exist_ok=True)
dbg.save(os.path.join(HERE, "stills", "card_debug.png"))
