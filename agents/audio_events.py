"""Аудио-события в записи стрима: резкие скачки громкости (рейдж, крик) и сильный смех.

loud  - кадры, где уровень на LOUD_DB дБ выше локальной медианы (±30 с), сгруппированные в события;
laugh - вероятность смеха по классификатору AudioSet (AST), окна 10 с с шагом 2.5 с.
"""
import json
import os
import subprocess

import numpy as np

SR = 16000
LOUD_DB = 9.0           # на сколько дБ выше локального уровня считаем скачком
MIN_ABS_DB = -38.0      # ниже этого уровня (тишина) скачки игнорируем
LAUGH_LABELS = ("laughter", "giggle", "chuckle", "belly laugh", "snicker", "chortle")


def _decode(path):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True)
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def loud_events(x, hop=0.25, win=0.5):
    h, w = int(SR * hop), int(SR * win)
    n = max((len(x) - w) // h, 0)
    if n < 10:
        return []
    frames = np.lib.stride_tricks.sliding_window_view(x, w)[::h][:n]
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    k = int(60 / hop)  # окно медианы ~60 с
    pad = np.pad(db, (k // 2, k // 2), mode="edge")
    base = np.median(np.lib.stride_tricks.sliding_window_view(pad, k)[: len(db)], axis=1)
    delta = db - base
    hot = (delta >= LOUD_DB) & (db > MIN_ABS_DB)
    events, i = [], 0
    while i < len(hot):
        if not hot[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(hot) and (hot[j + 1] or (j + 4 < len(hot) and hot[j + 1 : j + 5].any())):
            j += 1
        seg = delta[i : j + 1]
        events.append({"kind": "loud", "t0": round(i * hop, 1), "t1": round((j + 1) * hop + win, 1),
                       "peak_db": round(float(seg.max()), 1), "score": round(float(seg.max()) + 2 * (j - i + 1) * hop, 1)})
        i = j + 1
    return events


_clf = None


def _laugh_probs(x, win=10.0, hop=2.5):
    """Список (t0, вероятность смеха) по окнам. None, если классификатор недоступен."""
    global _clf
    try:
        import torch
        from transformers import ASTFeatureExtractor, ASTForAudioClassification
        if _clf is None:
            name = "MIT/ast-finetuned-audioset-10-10-0.4593"
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            fe = ASTFeatureExtractor.from_pretrained(name)
            m = ASTForAudioClassification.from_pretrained(name).to(dev).eval()
            ids = [i for i, l in m.config.id2label.items() if any(s in l.lower() for s in LAUGH_LABELS)]
            _clf = (fe, m, dev, ids)
            print(f"[audio] классификатор смеха на {dev}")
        fe, m, dev, ids = _clf
        wn, hp = int(SR * win), int(SR * hop)
        starts = list(range(0, max(len(x) - wn, 1), hp))
        out = []
        for b in range(0, len(starts), 16):
            chunk = [x[s : s + wn] for s in starts[b : b + 16]]
            inp = fe(chunk, sampling_rate=SR, return_tensors="pt").to(dev)
            with torch.no_grad():
                p = torch.sigmoid(m(**inp).logits)[:, ids].max(dim=1).values.cpu().numpy()
            out += [(s / SR, float(v)) for s, v in zip(starts[b : b + 16], p)]
        return out
    except Exception as e:
        print(f"[audio] смех не определяю ({str(e)[:120]})")
        return None


def laugh_events(x, thr=0.35):
    probs = _laugh_probs(x)
    if not probs:
        return []
    events, cur = [], None
    for t, p in probs:
        if p >= thr:
            if cur and t <= cur["t1"]:
                cur["t1"] = t + 10
                cur["p"] = max(cur["p"], p)
            else:
                cur = {"t0": t, "t1": t + 10, "p": p}
                events.append(cur)
    return [{"kind": "laugh", "t0": round(e["t0"], 1), "t1": round(e["t1"], 1), "p": round(e["p"], 2),
             "score": round(e["p"] * 20, 1)} for e in events]


def detect(path):
    """События аудио с кэшем: cache/<имя>.audio.json."""
    os.makedirs("cache", exist_ok=True)
    cache = os.path.join("cache", os.path.splitext(os.path.basename(path))[0] + ".audio.json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    x = _decode(path)
    ev = loud_events(x) + laugh_events(x)
    json.dump(ev, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return ev
