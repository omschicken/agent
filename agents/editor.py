"""Режет клип, делает 9:16 (размытый фон + оригинал по центру), баннер и дисклеймер 18+."""
import subprocess

FONT = "fontfile='C\\:/Windows/Fonts/arial.ttf':"  # на Linux/Mac поправьте путь


def _esc(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def render(src, start, end, out, brand):
    banner_raw = brand["banner_text"].format(**brand)
    banner_size = max(24, min(44, int(1000 / (len(banner_raw) * 0.6))))  # влезает в 1080px
    banner = _esc(banner_raw)
    disc = _esc(brand["disclaimer"])
    vf = (
        "[0:v]split[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5[bg];"
        "[b]scale=1080:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[v];"
        "[v]drawbox=x=0:y=1500:w=1080:h=130:color=black@0.65:t=fill,"
        f"drawtext={FONT}text='{banner}':fontcolor=white:fontsize={banner_size}:x=(w-text_w)/2:y=1535,"
        f"drawtext={FONT}text='{disc}':fontcolor=white@0.8:fontsize=28:x=(w-text_w)/2:y=1590[o]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", src,
         "-filter_complex", vf, "-map", "[o]", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", out],
        check=True,
    )
    return out
