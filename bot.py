import os
import random
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import yt_dlp

app = FastAPI()

# === Caminhos ===
BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
COOKIES_INSTAGRAM = BASE_DIR / "cookies_instagram.txt"
COOKIES_YOUTUBE = BASE_DIR / "cookies_youtube.txt"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# === Função para gravar cookies a partir de variáveis de ambiente ===
def salvar_cookie(env_name, file_path):
    if env_name in os.environ:
        conteudo = os.environ[env_name].replace("\\n", "\n").strip()
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(conteudo)
        print(f"[OK] Cookie salvo: {env_name}")
    else:
        print(f"[Aviso] Cookie {env_name} não encontrado no ambiente.")


# === Inicialização dos cookies ===
salvar_cookie("COOKIES_INSTAGRAM", COOKIES_INSTAGRAM)
salvar_cookie("COOKIES_YOUTUBE", COOKIES_YOUTUBE)


# === Configuração yt-dlp ===
def get_ydl_opts(url, out_template):
    opts = {
        "outtmpl": str(out_template),
        "quiet": True,
        "ratelimit": 1024 * 1024,  # 1 MB/s (anti 429)
        "retries": 10,
        "sleep_interval_requests": 1,
        "sleep_interval": 1,
        "sleep_interval_range": [1, 3],
        "noplaylist": True,
    }

    # Define cookie automaticamente com base na URL
    if "instagram.com" in url and COOKIES_INSTAGRAM.exists():
        opts["cookiefile"] = str(COOKIES_INSTAGRAM)
    elif "youtube.com" in url or "youtu.be" in url:
        if COOKIES_YOUTUBE.exists():
            opts["cookiefile"] = str(COOKIES_YOUTUBE)

    return opts


# === Endpoint de download ===
@app.get("/download")
def baixar_midia(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL é obrigatória.")

    try:
        nome_base = f"{random.randint(1000, 9999)}"
        out_template = DOWNLOAD_DIR / f"{nome_base}.%(ext)s"
        ydl_opts = get_ydl_opts(url, out_template)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            arquivo_final = ydl.prepare_filename(info)

        if not Path(arquivo_final).exists():
            raise HTTPException(status_code=404, detail="Arquivo não encontrado após o download.")

        return FileResponse(
            arquivo_final,
            media_type="application/octet-stream",
            filename=os.path.basename(arquivo_final)
        )

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao baixar mídia: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Endpoint de verificação ===
@app.get("/")
def raiz():
    return {"ok": True, "mensagem": "Bot online e pronto 🚀"}
