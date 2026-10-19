"""Рендер анимированного баннера CaseCrow: banner.html -> кадры PNG с прозрачностью -> casecrow_banner.mov (qtrle, альфа).

python banner/render_banner.py [секунд=20] [fps=30]      # полный рендер
python banner/render_banner.py stills 0.5 2 3.4 5.2      # только кадры-превью в banner/stills/
"""
import os
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = "file:///" + os.path.join(HERE, os.environ.get("BANNER_HTML", "banner.html")).replace("\\", "/")
HEIGHT = int(os.environ.get("BANNER_H", "260"))
OUT_NAME = os.environ.get("BANNER_OUT", "casecrow_banner.mov")


def open_page(p):
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1080, "height": HEIGHT}, device_scale_factor=1)
    page.goto(HTML)
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(1200)  # шрифты и первый кадр
    return browser, page


def shot(page, t, path):
    page.evaluate(f"setT({t * 1000})")
    page.screenshot(path=path, omit_background=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    with sync_playwright() as p:
        browser, page = open_page(p)
        if args and args[0] == "stills":
            os.makedirs(os.path.join(HERE, "stills"), exist_ok=True)
            for t in map(float, args[1:]):
                shot(page, t, os.path.join(HERE, "stills", f"t{t:g}.png"))
                print("still", t)
        else:
            dur = float(args[0]) if args else 20.0
            fps = int(args[1]) if len(args) > 1 else 30
            out = os.path.join(HERE, OUT_NAME)
            with tempfile.TemporaryDirectory() as tmp:
                n = int(dur * fps)
                for i in range(n):
                    shot(page, i / fps, os.path.join(tmp, f"{i:05d}.png"))
                    if i % 60 == 0:
                        print(f"кадр {i}/{n}")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i",
                                os.path.join(tmp, "%05d.png"), "-c:v", "qtrle", "-pix_fmt", "argb", out], check=True)
            print("готово:", out, f"{os.path.getsize(out) / 1e6:.1f} МБ")
        browser.close()
