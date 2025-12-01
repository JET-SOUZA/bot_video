async def baixar_video_youtube(url, output_dir, chat_id=None):
    """
    Faz download do YouTube com yt-dlp no Docker, suportando:
    - vídeos até 1080p
    - áudio mp3/m4a
    - shorts, lives processadas, vídeos age-restricted com cookies
    """

    import yt_dlp
    import datetime
    import os

    agora = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    saida_mp4 = os.path.join(output_dir, f"{chat_id}-{agora}.mp4")
    saida_mp3 = os.path.join(output_dir, f"{chat_id}-{agora}.mp3")

    ydl_opts = {
        "outtmpl": saida_mp4,
        "noplaylist": True,
        "quiet": True,
        "merge_output_format": "mp4",
        "cookiefile": "cookies_youtube.txt",  # se você usa cookies, ok
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4"
        }],
        "format": (
            "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080]+bestaudio/best"
        ),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # Se o Telegram pediu apenas o áudio
        if "audio_only" in url:
            import subprocess
            cmd = [
                "ffmpeg",
                "-i", saida_mp4,
                "-vn",
                "-acodec", "mp3",
                saida_mp3,
                "-y"
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return saida_mp3

        return saida_mp4

    except Exception as e:
        raise Exception(f"[yt_dlp module error] {e}")
