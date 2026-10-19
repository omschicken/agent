"""Логотип: светлый фон -> настоящая прозрачность. Чёрный силуэт с мягкими бликами остаётся (альфа по яркости).

python banner/make_logo.py <исходник.png> [выход=banner/crow.png]
Ещё делает превью на светлом и тёмном фоне: banner/stills/logo_check.png
"""
import os
import sys

import numpy as np
from PIL import Image

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "crow.png")

im = Image.open(src).convert("RGB")
a = np.asarray(im).astype(np.float32) / 255.0
lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)

# фон = медиана по краям изображения
edge = np.concatenate([lum[:12].ravel(), lum[-12:].ravel(), lum[:, :12].ravel(), lum[:, -12:].ravel()])
bg = float(np.median(edge))
alpha = np.clip((bg - lum) / bg, 0.0, 1.0)
alpha = np.where(alpha < 0.035, 0.0, alpha)  # убираем шум фона
alpha = np.clip(alpha * 1.04, 0, 1)

rgba = np.zeros((*lum.shape, 4), dtype=np.uint8)
rgba[..., 3] = (alpha * 255).astype(np.uint8)  # цвет чёрный (0,0,0), прозрачность несёт форму и блики
img = Image.fromarray(rgba, "RGBA")

# обрезаем по содержимому с небольшим полем
bbox = img.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox()
pad = 6
bbox = (max(bbox[0] - pad, 0), max(bbox[1] - pad, 0), min(bbox[2] + pad, img.width), min(bbox[3] + pad, img.height))
img = img.crop(bbox)
img.thumbnail((900, 900), Image.LANCZOS)
img.save(out)
print(f"фон {bg:.3f}; логотип {img.width}x{img.height} -> {out}")

# проверка на разных фонах
os.makedirs(os.path.join(os.path.dirname(out), "stills"), exist_ok=True)
sheet = Image.new("RGB", (img.width * 2 + 60, img.height + 40), (60, 60, 60))
for i, col in enumerate([(244, 241, 234), (30, 34, 44)]):
    tile = Image.new("RGB", (img.width + 20, img.height + 20), col)
    tile.paste(img, (10, 10), img)
    sheet.paste(tile, (20 + i * (img.width + 30), 10))
sheet.thumbnail((1200, 700))
sheet.save(os.path.join(os.path.dirname(out), "stills", "logo_check.png"))
