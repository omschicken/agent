"""Совмещение слоёв (кейс, автомат) с эталонным баннером: находим масштаб, поворот и положение, как их поставил GPT.

python banner/align.py <эталонный_баннер.png>
Печатает преобразования и сохраняет banner/align.json и проверочную картинку banner/stills/align_check.png.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ref_path = sys.argv[1]
ref = cv2.imread(ref_path, cv2.IMREAD_COLOR)
ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
sift = cv2.SIFT_create(nfeatures=6000)
kp2, des2 = sift.detectAndCompute(ref_gray, None)
print("эталон:", ref.shape[1], "x", ref.shape[0], "точек:", len(kp2))

PRE = 0.45  # слои уменьшаем до масштаба, близкого к эталону
result = {}
overlay = ref.copy()
for name in ("case", "rifle"):
    rgba = np.asarray(Image.open(os.path.join(HERE, "assets", f"{name}.png")).convert("RGBA"))
    h, w = rgba.shape[:2]
    small = cv2.resize(rgba, (int(w * PRE), int(h * PRE)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small[..., :3][..., ::-1], cv2.COLOR_BGR2GRAY)
    mask = (small[..., 3] > 220).astype(np.uint8) * 255
    mask = cv2.erode(mask, np.ones((5, 5), np.uint8))
    kp1, des1 = sift.detectAndCompute(gray, mask)
    bf = cv2.BFMatcher(cv2.NORM_L2)
    good = [m for m, n in bf.knnMatch(des1, des2, k=2) if m.distance < 0.78 * n.distance]
    print(f"{name}: точек слоя {len(kp1)}, хороших совпадений {len(good)}")
    if len(good) < 8:
        continue
    src = np.float32([kp1[m.queryIdx].pt for m in good]) / PRE  # в пикселях исходного слоя
    dst = np.float32([kp2[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=6.0)
    if M is None:
        continue
    a, b, tx, ty = M[0, 0], M[1, 0], M[0, 2], M[1, 2]
    s, rot = math.hypot(a, b), math.degrees(math.atan2(b, a))
    n_in = int(inl.sum())
    # где окажутся углы слоя (рамка) в эталоне
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    placed = (M[:, :2] @ corners.T).T + M[:, 2]
    result[name] = {"scale": s, "rot_deg": rot, "tx": float(tx), "ty": float(ty), "inliers": n_in, "good": len(good),
                    "layer_size": [w, h], "corners": placed.tolist(), "M": M.tolist()}
    print(f"   масштаб {s:.4f} (слой {w}x{h} -> {w * s:.0f}x{h * s:.0f} px), поворот {rot:.1f} градусов, "
          f"сдвиг ({tx:.0f}, {ty:.0f}), совпадений по RANSAC {n_in}")
    # проверочное наложение: слой, перенесённый в эталон, полупрозрачно
    warped = cv2.warpAffine(rgba, M, (ref.shape[1], ref.shape[0]), flags=cv2.INTER_AREA)
    al = (warped[..., 3:4].astype(np.float32) / 255.0) * 0.55
    col = np.where(name == "case", np.array([0, 0, 255]), np.array([255, 0, 0]))  # красный = кейс, синий = автомат
    overlay = (overlay.astype(np.float32) * (1 - al) + col.astype(np.float32) * al).astype(np.uint8)

json.dump(result, open(os.path.join(HERE, "align.json"), "w"), ensure_ascii=False, indent=1)
os.makedirs(os.path.join(HERE, "stills"), exist_ok=True)
cv2.imwrite(os.path.join(HERE, "stills", "align_check.png"), overlay)
if "case" in result and "rifle" in result:
    c, r = result["case"], result["rifle"]
    print(f"отношение масштабов автомат/кейс: {r['scale'] / c['scale']:.3f}, разница поворотов: {r['rot_deg'] - c['rot_deg']:.1f} градусов")
