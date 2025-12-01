def download_youtube_file(url: str, quality="480", to_mp3=False, cookiefile=None, timeout=120):
    _ensure_ffmpeg_available()

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    basename = f"video-{timestamp}"
    outtmpl = str(DOWNLOAD_DIR / f"{basename}.%(ext)s")

    # Formato base (todas as qualidades incluídas)
    base_format = get_format_for_quality(quality, to_mp3)

    ytdl_opts = {
        "outtmpl": outtmpl,
        "format": f"{base_format}/bestvideo*+bestaudio/best",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,

        # Download rápido e seguro
        "concurrent_fragment_downloads": 5,
        "retries": 5,
        "fragment_retries": 5,
        "skip_unavailable_fragments": True,

        # Evitar SABR forcing
        "hls_use_mpegts": False,
        "extractor_args": {"youtube": {"player_client": ["web"]}},

        "socket_timeout": 15,
        "merge_output_format": "mp4",
        "postprocessor_args": ["-movflags", "faststart"],
    }

    if cookiefile:
        ytdl_opts["cookiefile"] = cookiefile

    if to_mp3:
        ytdl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    # --- Prefer yt_dlp module ---
    if _HAS_YT_DLP_MODULE:
        try:
            with ytdlp_module.YoutubeDL(ytdl_opts) as ydl:
                ydl.download([url])
            final = _find_final_file(basename)
            if final:
                return final
            raise FileNotFoundError("Arquivo final não encontrado.")
        except Exception as e:
            raise Exception(f"[yt_dlp module error] {e}")

    # --- fallback: binary ---
    binary = _check_executable("yt-dlp")
    if not binary:
        raise RuntimeError("yt-dlp não encontrado no ambiente.")

    cmd = [
        binary,
        "-o", outtmpl,
        "-f", ytdl_opts["format"],
        "--no-playlist",
        "--retries", "5",
        "--fragment-retries", "5",
        "--skip-unavailable-fragments",
        "--socket-timeout", "15",
        "--merge-output-format", "mp4",
        "--postprocessor-args", "-movflags faststart",
        url,
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if proc.returncode != 0:
        raise Exception(f"[yt-dlp binary error]\n{proc.stderr[-1500:]}")

    final = _find_final_file(basename)
    if final:
        return final

    raise FileNotFoundError("Arquivo final não encontrado.")
