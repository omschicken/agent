"""Вырезает ворона из готовой карточки (banner/card.png) в banner/crow2.png и печатает цвет фона слева."""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BOX = (16, 50, 310, 350)  # область ворона в пикселях карточки (1955x460)

card = Image.open(os.path.join(HERE, "card.png")).convert("RGB")
crop = card.crop(BOX)
a = np.asarray(crop).astype(np.float32) / 255.0
lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)

# фон вокруг ворона = светлый крем: оцениваем по углам области
corners = np.concatenate([lum[:8, :8].ravel(), lum[:8, -8:].ravel(), lum[-8:, :8].ravel(), lum[-8:, -8:].ravel()])
bg = float(np.median(corners))
alpha = np.clip((bg - lum) / bg, 0, 1)
alpha = np.where(alpha < 0.05, 0, np.clip(alpha * 1.05, 0, 1))
rgba = np.zeros((*lum.shape, 4), dtype=np.uint8)
rgba[..., 3] = (alpha * 255).astype(np.uint8)
Image.fromarray(rgba, "RGBA").save(os.path.join(HERE, "crow2.png"))

cream = np.asarray(card.crop((330, 10, 480, 40))).reshape(-1, 3).mean(axis=0)
print("crow2.png", crop.size, "фон области:", f"{bg:.3f}", "цвет крема: #%02X%02X%02X" % tuple(int(v) for v in cream))
