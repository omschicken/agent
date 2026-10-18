"""Отладка детектора смеха: топ окон по вероятности смеха + что слышно в этих местах."""
import json
import sys

from agents import audio_events as ae

path = sys.argv[1]
x = ae._decode(path)
print(f"аудио: {len(x) / ae.SR / 60:.1f} мин")
probs = ae._laugh_probs(x)
if probs is None:
    sys.exit("классификатор недоступен")
fe, m, dev, ids = ae._clf
print("метки смеха:", [m.config.id2label[i] for i in ids])
ps = sorted(probs, key=lambda z: -z[1])
print("топ-12 окон (время с, вероятность):")
for t, p in ps[:12]:
    print(f"  {t:7.1f}  {p:.3f}")
print("окон >0.10:", sum(p > 0.10 for _, p in probs), " >0.20:", sum(p > 0.20 for _, p in probs),
      " >0.35:", sum(p > 0.35 for _, p in probs), " из", len(probs))
