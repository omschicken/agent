"""Запуск внешних программ (ffmpeg/ffprobe) с повтором.

В Windows алиас ffmpeg от winget периодически отказывает в доступе, поэтому ищем настоящий ffmpeg.exe/ffprobe.exe
в пакетах winget и запускаем его по прямому пути; плюс повтор при PermissionError.
"""
import glob
import os
import shutil
import subprocess
import time

_cache = {}


def _resolve(name):
    if name in _cache:
        return _cache[name]
    path = None
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    hits = glob.glob(os.path.join(base, "**", f"{name}.exe"), recursive=True)
    if hits:
        path = hits[0]
    _cache[name] = path or shutil.which(name) or name
    return _cache[name]


def run(*args, retries=6, **kwargs):
    if args and isinstance(args[0], (list, tuple)) and args[0] and args[0][0] in ("ffmpeg", "ffprobe"):
        args = ([_resolve(args[0][0])] + list(args[0][1:]),) + tuple(args[1:])
    for i in range(retries):
        try:
            return subprocess.run(*args, **kwargs)
        except PermissionError:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))
