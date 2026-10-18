"""Публикация через официальные API. YouTube реализован, TikTok и Instagram - заглушки."""


def post_youtube(video, copy):
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secret.json", ["https://www.googleapis.com/auth/youtube.upload"]
    )
    yt = build("youtube", "v3", credentials=flow.run_local_server(port=0))
    tags = " ".join("#" + h.lstrip("#") for h in copy["hashtags"])
    body = {
        "snippet": {
            "title": copy["title"][:100],
            "description": f"{copy['description']}\n\n{tags} #Shorts",
            "categoryId": "20",
        },
        # private: сначала проверяем руками, потом открываем
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
    }
    return yt.videos().insert(
        part="snippet,status", body=body, media_body=MediaFileUpload(video)
    ).execute()


def post_tiktok(video, copy):
    # TikTok Content Posting API: нужно одобренное приложение и OAuth.
    print(f"[tiktok] TODO upload {video}")


def post_instagram(video, copy):
    # Instagram Graph API (Reels): бизнес-аккаунт, видео по публичному URL.
    print(f"[instagram] TODO upload {video}")


PUBLISHERS = {"youtube": post_youtube, "tiktok": post_tiktok, "instagram": post_instagram}
