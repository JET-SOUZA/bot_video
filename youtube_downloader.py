import os
import subprocess
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = SCRIPT_DIR / "downloads" / "youtube"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================
# FORMATO INTELIGENTE (corrigido)
# =====================================================
def get_format_for_quality(quality: str, to_mp3: bool):
    """
    Sempre retorna streams separados + áudio.
    YouTube raramente entrega vídeo+áudio juntos.
    """
    if to_mp3:
        return "bestaudio/best"

    table = {
        "144":  "bv*[height<=144]+ba/best",
        "240":  "bv*[height<=240]+ba/best",
        "360":  "bv*[height<=360]+ba/best",
        "480":  "bv*[height<=480]+ba/best",
        "720":  "bv*[height<=720]+ba/best",
        "1080": "bv*[height<=1080]+ba/best",
        "1440": "bv*[height<=1440]+ba/best",
        "2160": "bv*[height<=2160]+ba/best",
    }

    # fallback: melhor vídeo + melhor áudio
    return table.get(str(quality), "bv*+ba/best")


# =====================================================
# DOWNLOAD SEGURO VIA SUBPROCESS (não trava webhook)
# =====================================================
def download_youtube_file(url: str, quality="480", to_mp3=False, cookiefile=None):

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    basename = f"video-{timestamp}"

    # ——— Saída | MP3 vs MP4 ———
    if to_mp3:
        outtmpl = str(DOWNLOAD_DIR / f"{basename}.mp3")
    else:
        outtmpl = str(DOWNLOAD_DIR / f"{basename}.mp4")

    # ——— Comando yt-dlp ———
    cmd = [
        "yt-dlp",
        "-o", outtmpl,

        # Formato corrigido: sempre vídeo + áudio separado
        "-f", get_format_for_quality(quality, to_mp3),

        "--no-warnings",
        "--restrict-filenames",
        "--no-playlist",
        "--retries", "20",
        "--fragment-retries", "20",
        "--hls-use-mpegts",

        # Saída final deve ser MP4 sempre que não for MP3
        "--merge-output-format", "mp4",

        # Remove carga em players (Resolve erro do Render)
        "--postprocessor-args", "-movflags faststart",
    ]

    # Cookies opcionais
    if cookiefile:
        cmd += ["--cookies", cookiefile]

    # ——— Modo MP3 ———
    if to_mp3:
        cmd += [
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "192K",
        ]

    cmd.append(url)

    # ——— Executa (seguro) ———
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if process.returncode != 0:
        raise Exception(f"[YT-DLP ERRO]\n{process.stderr[-600:]}")

    # ——— Verifica fim ———
    filepath = outtmpl

    if not os.path.exists(filepath):
        files = list(DOWNLOAD_DIR.glob(f"{basename}*"))
        if files:
            filepath = str(files[0])
        else:
            raise FileNotFoundError("Arquivo final não encontrado após download.")

    return filepath
