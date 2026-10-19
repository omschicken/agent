"""Информация о видео/канале: название, длительность, главы, описание, последние ролики канала."""
import sys

from yt_dlp import YoutubeDL

url = sys.argv[1]
with YoutubeDL({"quiet": True, "skip_download": True}) as y:
    m = y.extract_info(url, download=False)
print("название :", m.get("title"))
print("канал    :", m.get("channel"), "|", m.get("channel_url"), "| подписчики:", m.get("channel_follower_count"))
print("длина    :", m.get("duration"), "с | просмотры:", m.get("view_count"), "| загружено:", m.get("upload_date"))
print("главы    :", len(m.get("chapters") or []))
for c in (m.get("chapters") or [])[:25]:
    print(f"   {c['start_time']:6.0f}-{c['end_time']:6.0f}  {c['title']}")
print("heatmap  :", "есть" if m.get("heatmap") else "нет")
print("описание :", (m.get("description") or "")[:900].replace("\n", " | "))
print("теги     :", ", ".join((m.get("tags") or [])[:15]))

ch = m.get("channel_url")
if ch and len(sys.argv) > 2:
    with YoutubeDL({"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": 12}) as y:
        es = y.extract_info(ch.rstrip("/") + "/videos", download=False).get("entries") or []
    print("\nпоследние ролики канала:")
    for e in es:
        print(f"   {e.get('duration') or 0:6.0f}с  {(e.get('view_count') or 0):>9,}  {e.get('title')}")
