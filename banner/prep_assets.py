"""Слои баннера (от GPT) -> banner/assets/*.png: проверка прозрачности и обрезка пустых полей.

Порядок и имена исходников в uploads: тень, кнопка, плашка промокода, автомат, кейс, фон.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
os.makedirs(OUT, exist_ok=True)

UP = r"C:\Users\mo\.claude\uploads\e61f2826-bce5-4f76-88f1-d6dd421b0e8e"
SRC = {
    "shadow": "255a2976-image.png",
    "button": "0366c978-image.png",
    "promo": "01003d60-image.png",
    "rifle": "86c30b85-image.png",
    "case": "5565f020-image.png",
    "bg": "c5baa42e-image.png",
}

meta = {}
for name, f in SRC.items():
    im = Image.open(os.path.join(UP, f))
    mode = im.mode
    if name == "bg":
        im.convert("RGB").save(os.path.join(OUT, "bg_full.png"))
        meta[name] = {"mode": mode, "size": im.size}
        print(name, mode, im.size)
        continue
    im = im.convert("RGBA")
    a = np.asarray(im)
    alpha = a[..., 3]
    has_alpha = alpha.min() < 250
    if not has_alpha:  # непрозрачный светлый фон -> прозрачность по яркости (тень чёрная)
        lum = a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32) / 255.0
        bg = float(np.median(np.concatenate([lum[:10].ravel(), lum[-10:].ravel()])))
        al = np.clip((bg - lum) / max(bg, 1e-3), 0, 1)
        out = np.zeros_like(a)
        out[..., 3] = (al * 255).astype(np.uint8)
        im = Image.fromarray(out, "RGBA")
        alpha = out[..., 3]
    bbox = Image.fromarray(alpha).point(lambda v: 255 if v > 14 else 0).getbbox()
    im = im.crop(bbox)
    im.save(os.path.join(OUT, f"{name}.png"))
    meta[name] = {"mode": mode, "had_alpha": bool(has_alpha), "size": im.size}
    print(f"{name}: {mode}, альфа {'есть' if has_alpha else 'сделана из яркости'}, после обрезки {im.size}")
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), ensure_ascii=False, indent=1)
