"""Измерения для посадки предметов на пол: нижняя кромка кейса/автомата в PNG и линия пола/стены на фоне."""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))

for name in ("case", "rifle"):
    im = Image.open(os.path.join(HERE, "assets", f"{name}.png")).convert("RGBA")
    a = np.asarray(im)[..., 3].astype(np.float32)
    h, w = a.shape
    cover = (a > 200).sum(axis=1)  # сколько пикселей в строке по-настоящему непрозрачны
    rows_solid = np.where(cover > 0.04 * w)[0]
    rows_any = np.where((a > 14).sum(axis=1) > 0)[0]
    print(f"{name}: размер {w}x{h}; граница любых пикселей {rows_any[-1]}; нижняя кромка твёрдого тела {rows_solid[-1]} "
          f"(разница {rows_any[-1] - rows_solid[-1]} px = {100 * (rows_any[-1] - rows_solid[-1]) / h:.1f}% высоты)")
    # профиль последних 12% высоты
    for frac in (0.80, 0.86, 0.90, 0.94, 0.97, 1.0):
        y = min(int(frac * h) - 1, h - 1)
        xs = np.where(a[y] > 200)[0]
        print(f"   на {int(frac * 100)}% высоты: твёрдых пикселей {len(xs)}" + (f", от x={xs[0]} до x={xs[-1]}" if len(xs) else ""))

# линия стена/пол на фоне: сильный горизонтальный перепад яркости по столбцам правой половины
card = Image.open(os.path.join(HERE, "card.png")).convert("L")
c = np.asarray(card).astype(np.float32)
H, W = c.shape
print(f"фон {W}x{H}")
for x0, x1 in ((1000, 1150), (1150, 1300), (1300, 1450), (1450, 1600), (1600, 1750), (1750, 1900)):
    col = c[:, x0:x1].mean(axis=1)
    g = np.abs(np.diff(col))
    g[:120] = 0  # игнорируем верх (тени листьев)
    g[400:] = 0
    y = int(np.argmax(g))
    print(f"   x {x0}-{x1}: сильнейший горизонтальный перепад на y={y} (яркость {col[y]:.0f}->{col[y + 1]:.0f})")
