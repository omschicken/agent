"""Расшифровка речи (faster-whisper, локально) с кэшем: cache/<имя файла>.<модель>.json.
Использует видеокарту NVIDIA (CUDA), если доступна; иначе процессор."""
import glob
import json
import os
import site

_model = None


def _add_cuda_dlls():
    """Windows: подхватываем cuBLAS/cuDNN из pip-пакетов nvidia-*-cu12."""
    for base in site.getsitepackages():
        for d in glob.glob(os.path.join(base, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(d)
            except (OSError, AttributeError):
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _load(model_size):
    from faster_whisper import WhisperModel
    _add_cuda_dlls()
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            m = WhisperModel(model_size, device="cuda", compute_type="float16")
            print(f"[whisper] {model_size} на GPU")
            return m
    except Exception as e:
        print(f"[whisper] GPU недоступен ({str(e)[:100]}), использую процессор")
    print(f"[whisper] {model_size} на процессоре (медленно)")
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe(path, model_size="large-v3-turbo", language="ru"):
    """Возвращает [{'start': сек, 'end': сек, 'text': '...'}]."""
    os.makedirs("cache", exist_ok=True)
    cache = os.path.join("cache", os.path.splitext(os.path.basename(path))[0] + f".{model_size}.json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))

    global _model
    if _model is None:
        _model = _load(model_size)
    segs, _ = _model.transcribe(path, language=language, vad_filter=True, beam_size=1,
                                condition_on_previous_text=False)
    out = [{"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()} for s in segs]
    json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return out
