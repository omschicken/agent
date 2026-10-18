"""Разведчик: сам ищет и скачивает видео для нарезки.

Источники:
  - поисковые запросы YouTube (config.yaml -> scout.queries), сортировка по просмотрам за свежий период
  - sources.yaml: channels (каналы/плейлисты) и urls (любые ссылки, что понимает yt-dlp: YouTube, Twitch, X, Reddit...)
  - sources.yaml: blocklist - каналы, которые не трогаем (например, попросили убрать)
Рядом с видео пишется <id>.txt с названием и источником (идёт в тексты постов).
"""
import itertools
import json
import os
import re
from urllib.parse import quote_plus

import yaml
from yt_dlp import YoutubeDL

SEEN = "seen.json"
# sp-параметры поиска YouTube: фильтр "эта неделя/месяц" + сортировка по просмотрам
SP = {"week": "CAMSBAgDEAE%253D", "month": "CAMSBAgEEAE%253D", "any": "CAMSAhAB"}


def _seen():
    return set(json.load(open(SEEN, encoding="utf-8"))) if os.path.exists(SEEN) else set()


def _save_seen(s):
    json.dump(sorted(s), open(SEEN, "w", encoding="utf-8"))


def _info(url, **opts):
    with YoutubeDL({"quiet": True, "skip_download": True, "noprogress": True, **opts}) as y:
        return y.extract_info(url, download=False)


def _search(query, limit, period):
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={SP.get(period, SP['any'])}"
    res = _info(url, extract_flat=True, playlistend=limit)
    return [(e["id"], f"https://www.youtube.com/watch?v={e['id']}") for e in (res.get("entries") or []) if e.get("id")]


def _from_sources(path, limit):
    if not os.path.exists(path):
        return [], set()
    cfg = yaml.safe_load(open(path, encoding="utf-8")) or {}
    per_channel = []
    for url in (cfg.get("channels") or []) + (cfg.get("urls") or []):
        try:
            res = _info(url, extract_flat=True, playlistend=limit)
        except Exception as e:
            print(f"[scout] {url}: пропуск ({e})")
            continue
        per_channel.append([(e["id"], e.get("url") or e.get("webpage_url") or url)
                            for e in (res.get("entries") or [res]) if e.get("id")])
    out = [x for row in itertools.zip_longest(*per_channel) for x in row if x]  # по кругу: по видео с каждого канала
    return out, {b.lower() for b in (cfg.get("blocklist") or [])}


def _is_russian(m):
    lang = (m.get("language") or "").lower()
    if lang:
        return lang.startswith("ru")
    letters = [c for c in (m.get("title") or "") if c.isalpha()]
    return bool(letters) and sum("Ѐ" <= c <= "ӿ" for c in letters) / len(letters) >= 0.4


def _vet(m, lang, model):
    """Claude по названию/описанию решает: один цельный момент (клатч, фейл, лайфхак, кейс), а не сборка."""
    import anthropic

    if lang == "trusted":  # автор из белого списка: берём рейджи, смешное и хайлайты, нарезки допустимы
        need = ("Нужны: рейджи (эмоциональные срывы), смешные моменты и фейлы, сильные хайлайты (клатч/эйс). "
                "Нарезки из нескольких моментов допустимы - мы режем их по сценам. НЕ подходят: разговорные стримы, "
                "настройки/гайды без игры, новости, розыгрыши, видео про другие игры.")
    else:
        want = "на русском языке" if lang == "ru" else "любой язык, турнирный/про-хайлайт"
        need = ("Нужны: смешной или полезный контент (лайфхак, раскидка, фишка), открытие кейсов или одиночный "
                "сильный момент. НЕ подходят: сборки из многих моментов разных игроков, фрагмуви, топы, новости, "
                f"длинные стримы, другие игры. Язык: {want}.")
    prompt = f"""Видео про CS2. Название: {m.get('title')}
Канал: {m.get('uploader')}; длительность: {m.get('duration')} c
Описание: {(m.get('description') or '')[:600]}
Теги: {', '.join((m.get('tags') or [])[:15])}
Материал идёт в короткие вертикальные видео. {need}
Ответь только JSON: {{"ok": true/false, "reason": "кратко"}}"""
    try:
        r = anthropic.Anthropic().messages.create(
            model=model, max_tokens=500, messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in r.content if b.type == "text").strip().strip("`").removeprefix("json").strip()
        j = json.loads(text)
        return bool(j.get("ok")), j.get("reason", "")
    except Exception as e:  # нет денег/сети - не блокируем разведчика, фильтры по словам уже отработали
        print(f"[scout] vet недоступен ({e})")
        return True, ""


def _download(url, dest, max_height):
    opts = {
        "quiet": True, "noprogress": True,
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(dest, "%(id)s.%(ext)s"),
    }
    with YoutubeDL(opts) as y:
        y.download([url])


def scout(cfg, dest="inbox", sources_file="sources.yaml"):
    sc = cfg.get("scout", {})
    seen = _seen()
    src, blocked = _from_sources(sources_file, sc.get("per_query", 8))
    src_ids = {v for v, _ in src}
    cands = [(v, u, "any") for v, u in src]
    queries = [] if (sc.get("whitelist_only") and src) else sc.get("queries", [])  # только белый список каналов
    for q in queries:
        q = {"q": q, "lang": "any"} if isinstance(q, str) else q
        cands += [(v, u, q.get("lang", "any")) for v, u in
                  _search(q["q"], sc.get("per_query", 8), sc.get("period", "week"))]

    got = 0
    langs = {}
    for v, u, lg in cands:
        langs.setdefault(v, (u, lg))
    for vid, (url, lang) in langs.items():
        if vid in seen:
            continue
        if got >= sc.get("max_new_videos", 3):
            break
        try:
            m = _info(url)
        except Exception as e:
            print(f"[scout] {vid}: пропуск ({e})")
            continue
        seen.add(vid)
        author = (m.get("uploader") or m.get("channel") or "").lower()
        if any(b in author for b in blocked):
            continue
        if not (sc.get("min_duration", 60) <= (m.get("duration") or 0) <= sc.get("max_duration", 1800)):
            print(f"[scout] {vid}: длительность {m.get('duration')}с вне диапазона — {m.get('title')}")
            continue
        if vid not in src_ids and (m.get("view_count") or 0) < sc.get("min_views", 0):
            continue
        title = (m.get("title") or "").lower()
        trusted = vid in src_ids  # канал из белого списка: слова «нарезка/моменты» там нормальны
        excl = sc.get("exclude_whitelist", ["розыгрыш", "giveaway", "конкурс", "раздача"]) if trusted else sc.get("exclude", [])
        bad = next((x for x in excl if x.lower() in title), None)
        if not bad and not trusted and re.search(r"#\s?\d+|episode \d+|part \d+|vol\.? ?\d+", title):
            bad = "номер выпуска (серия-сборник)"
        if bad:
            print(f"[scout] {vid}: сборка/нерелевантно ('{bad}'), пропуск — {m.get('title')}")
            continue
        kws = [k.lower() for k in sc.get("keywords", [])]
        text = " ".join([m.get("title") or "", " ".join(m.get("tags") or [])]).lower()
        if kws and not trusted and not any(k in text for k in kws):
            print(f"[scout] {vid}: не про CS, пропуск — {m.get('title')}")
            continue
        if lang == "ru" and not _is_russian(m):
            print(f"[scout] {vid}: не на русском, пропуск — {m.get('title')}")
            continue
        if sc.get("vet") and os.environ.get("ANTHROPIC_API_KEY"):
            ok, why = _vet(m, "trusted" if trusted else lang, cfg.get("model", "claude-sonnet-5-5"))
            if not ok:
                print(f"[scout] {vid}: Claude отклонил ({why}) — {m.get('title')}")
                continue
        try:
            _download(url, dest, sc.get("max_height", 1080))
        except Exception as e:
            print(f"[scout] {vid}: не скачалось ({str(e)[:120]})")
            continue
        credit = (
            f"{m.get('title')}\n"
            f"Источник: «{m.get('title')}», канал {m.get('uploader')}, {m.get('webpage_url')}"
        )
        # имя файла берём как скачал yt-dlp (id.ext), заметку кладём рядом
        open(os.path.join(dest, f"{m['id']}.txt"), "w", encoding="utf-8").write(credit)
        got += 1
        print(f"[scout] скачано: {m['id']} — {m.get('title')}")
    _save_seen(seen)
    return got
