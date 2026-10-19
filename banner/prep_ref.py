"""Эталонный баннер (готовая картинка GPT) -> banner/card_ref.png (карточка со скруглёнными углами),
banner/crow_ref.png (ворон из карточки для вступления) и сетка-разметка banner/stills/ref_debug.png.

python banner/prep_ref.py <эталон.png>
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
im = Image.open(sys.argv[1]).convert("RGB")
a = np.asarray(im).astype(np.float32)
lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
bright = lum > 95
cols = np.where(bright.mean(axis=0) > 0.30)[0]
rows = np.where(bright.mean(axis=1) > 0.30)[0]
x0, x1, y0, y1 = int(cols[0]), int(cols[-1]) + 1, int(rows[0]), int(rows[-1]) + 1
top = np.where(bright[y0 + 1, x0:x1])[0]
radius = max(30, min(int(top[0]) + 2 if len(top) else 56, 90))

card = im.crop((x0, y0, x1, y1))
w, h = card.size
mask = Image.new("L", (w * 2, h * 2), 0)
ImageDraw.Draw(mask).rounded_rectangle((1, 1, w * 2 - 2, h * 2 - 2), radius=radius * 2, fill=255)
out = card.convert("RGBA")
out.putalpha(mask.resize((w, h), Image.LANCZOS))
out.save(os.path.join(HERE, "card_ref.png"))
print(f"карточка эталона {w}x{h}, рамка {x0},{y0}-{x1},{y1}, радиус {radius}")

# ворон: область слева, фон крем
BOX = (12, 50, 312, 395)
crop = card.crop(BOX)
c = np.asarray(crop).astype(np.float32) / 255.0
cl = c @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
corners = np.concatenate([cl[:8, :8].ravel(), cl[:8, -8:].ravel(), cl[-8:, :8].ravel(), cl[-8:, -8:].ravel()])
bg = float(np.median(corners))
al = np.clip((bg - cl) / bg, 0, 1)
al = np.where(al < 0.05, 0, np.clip(al * 1.05, 0, 1))
rgba = np.zeros((*cl.shape, 4), dtype=np.uint8)
rgba[..., 3] = (al * 255).astype(np.uint8)
Image.fromarray(rgba, "RGBA").save(os.path.join(HERE, "crow_ref.png"))
print("ворон", crop.size, "фон области %.3f" % bg)

dbg = out.convert("RGB").copy()
d = ImageDraw.Draw(dbg)
for gx in range(0, w, 100):
    d.line((gx, 0, gx, h), fill=(255, 0, 0), width=1)
    d.text((gx + 3, 3), str(gx), fill=(255, 0, 0))
for gy in range(0, h, 100):
    d.line((0, gy, w, gy), fill=(0, 120, 255), width=1)
    d.text((3, gy + 3), str(gy), fill=(0, 120, 255))
d.rectangle(BOX, outline=(0, 200, 0), width=2)
os.makedirs(os.path.join(HERE, "stills"), exist_ok=True)
dbg.save(os.path.join(HERE, "stills", "ref_debug.png"))
