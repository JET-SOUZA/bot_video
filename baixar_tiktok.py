from yt_dlp import YoutubeDL

COOKIES_TIKTOK = "cookies.txt"  # caminho do seu arquivo de cookies
URL_TIKTOK = "https://www.tiktok.com/@sophiabianco_/video/7562518272764284168"

ydl_opts = {
    "outtmpl": "%(title)s.%(ext)s",
    "format": "bestvideo+bestaudio/best",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "ignoreerrors": True,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "retries": 3,
    "no_warnings": True,
    "cookiefile": COOKIES_TIKTOK,
    "browser_executable": r"C:\Users\Sunrocha 03\Documents\Jonathan - Opções binárias\boot telegram\Chrome-bin\chrome.exe"
}

with YoutubeDL(ydl_opts) as ydl:
    ydl.download([URL_TIKTOK])
