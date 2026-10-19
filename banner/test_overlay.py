"""Проверка наложения баннера-видео на клип: python banner/test_overlay.py <баннер.mov|webm> <клип.mp4> <выход.mp4>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents import editor  # noqa: E402

banner, src, out = sys.argv[1], sys.argv[2], sys.argv[3]
brand = {"banner_video": banner, "banner_delay": 1.0, "banner_bottom": 240}
editor.render(src, 0, 14, out, brand)
print("готово:", out)
