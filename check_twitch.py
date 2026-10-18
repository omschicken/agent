"""Проверка: топ-клипы стримера на Twitch (по просмотрам) и привязка к записи стрима (VOD + смещение)."""
import json
import sys
import urllib.request

GQL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # публичный web-клиент Twitch (тот же использует сайт twitch.tv)

QUERY = """query($login:String!, $period:ClipsPeriod!, $n:Int!){
  user(login:$login){ displayName
    clips(first:$n, criteria:{period:$period, sort:VIEWS_DESC}){
      edges{ node{ slug title viewCount durationSeconds createdAt
                   curator{ login } game{ name } videoOffsetSeconds video{ id } } } } } }"""


def top_clips(login, period="LAST_WEEK", n=10):
    body = json.dumps({"query": QUERY, "variables": {"login": login, "period": period, "n": n}}).encode()
    req = urllib.request.Request(GQL, body, {"Client-ID": CLIENT_ID, "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=30))
    u = (r.get("data") or {}).get("user")
    return [e["node"] for e in (u["clips"]["edges"] if u else [])]


if __name__ == "__main__":
    for login in sys.argv[1:] or ["buster"]:
        try:
            cl = top_clips(login)
        except Exception as e:
            print(login, "ERR", e)
            continue
        print(f"\n== {login}: {len(cl)} клипов за неделю")
        for c in cl[:6]:
            vid = (c.get("video") or {}).get("id")
            print(f"  {c['viewCount']:>6} просм | {c['durationSeconds']:.0f}с | {(c.get('game') or {}).get('name')} | "
                  f"VOD {vid} @ {c.get('videoOffsetSeconds')}с | {c['title'][:50]}")
