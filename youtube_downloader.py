import os
import subprocess
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = SCRIPT_DIR / "downloads" / "youtube"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------
# FORMATS
# --------------------------------------------
def get_format_for_quality(quality: str, to_mp3: bool):
    if to_mp3:
        return "bestaudio/best"

    table = {
        "360":  "bestvideo[height<=360]+bestaudio/best",
        "480":  "bestvideo[height<=480]+bestaudio/best",
        "720":  "bestvideo[height<=720]+bestaudio/best",
        "1080": "bestvideo[height<=1080]+bestaudio/best",
        "1440": "bestvideo[height<=1440]+bestaudio/best",
        "2160": "bestvideo[height<=2160]+bestaudio/best",
    }
    return table.get(str(quality), "bestvideo+bestaudio/best")


# --------------------------------------------
# SUBPROCESS YT-DLP (NÃO TRAVA RENDER FREE)
# --------------------------------------------
def download_youtube_file(url: str, quality="480", to_mp3=False, cookiefile=None):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    basename = f"video-{timestamp}"

    # MP3 → exige outro template
    if to_mp3:
        outtmpl = str(DOWNLOAD_DIR / f"{basename}.mp3")
    else:
        outtmpl = str(DOWNLOAD_DIR / f"{basename}.mp4")

    # monta comando yt-dlp
    cmd = [
        "yt-dlp",
        "-o", outtmpl,
        "-f", get_format_for_quality(quality, to_mp3),
        "--no-warnings",
        "--restrict-filenames",
        "--no-playlist",
        "--retries", "20",
        "--fragment-retries", "20",
        "--hls-use-mpegts",
        "--merge-output-format", "mp4",
        "--postprocessor-args", "-movflags faststart",
    ]

    if cookiefile:
        cmd += ["--cookies", cookiefile]

    if to_mp3:
        cmd += [
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "192K",
        ]

    cmd.append(url)

    # ---- RUN (BLOQUEIO ISOLADO → NÃO TRAVA WEBHOOK) ----
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if process.returncode != 0:
        raise Exception(f"yt-dlp erro: {process.stderr[-500:]}")

    # identifica arquivo final
    if to_mp3:
        filepath = outtmpl
    else:
        filepath = outtmpl.replace(".mp4", ".mp4")

    if not os.path.exists(filepath):
        # fallback: tenta achar arquivo gerado no diretório
        files = list(DOWNLOAD_DIR.glob(f"{basename}*"))
        if files:
            filepath = str(files[0])
        else:
            raise FileNotFoundError("Arquivo final não encontrado após download.")

    return filepath
