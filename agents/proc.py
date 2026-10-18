"""Запуск внешних программ (ffmpeg/ffprobe) с повтором: Windows иногда на секунду отказывает в доступе."""
import subprocess
import time


def run(*args, retries=5, **kwargs):
    for i in range(retries):
        try:
            return subprocess.run(*args, **kwargs)
        except PermissionError:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))
