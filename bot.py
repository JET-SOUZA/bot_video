import os
import yt_dlp
from fastapi import FastAPI, Request
import uvicorn

# ======================================================
# 🔧 1. CONFIGURAÇÃO DE COOKIES (Instagram, YouTube, TikTok, Twitter)
# ======================================================

def salvar_cookie(nome_env, arquivo):
    conteudo = os.getenv(nome_env)
    if not conteudo:
        print(f"[⚠️] Variável {nome_env} não encontrada.")
        return
    caminho = f"/opt/render/project/src/{arquivo}"
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    print(f"[OK] Cookie salvo: {nome_env}")

# Salva cookies (se existirem)
salvar_cookie("COOKIES_INSTAGRAM", "cookies_instagram.txt")
salvar_cookie("COOKIES_YOUTUBE", "cookies_youtube.txt")
salvar_cookie("COOKIES_TIKTOK", "cookies_tiktok.txt")
salvar_cookie("COOKIES_TWITTER", "cookies_twitter.txt")


# ======================================================
# ⚙️ 2. FUNÇÃO DE DOWNLOAD UNIVERSAL
# ======================================================

def baixar_midia(url: str):
    """
    Faz download de vídeos/fotos de qualquer site suportado (Instagram, YouTube, TikTok, Twitter, etc.)
    usando yt-dlp e cookies, se disponíveis.
    """
    saida = "/opt/render/project/src/downloads/%(title)s.%(ext)s"
    os.makedirs("/opt/render/project/src/downloads", exist_ok=True)

    cookies_file = None
    if "instagram.com" in url:
        cookies_file = "/opt/render/project/src/cookies_instagram.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        cookies_file = "/opt/render/project/src/cookies_youtube.txt"
    elif "tiktok.com" in url:
        cookies_file = "/opt/render/project/src/cookies_tiktok.txt"
    elif "x.com" in url or "twitter.com" in url:
        cookies_file = "/opt/render/project/src/cookies_twitter.txt"

    ydl_opts = {
        "outtmpl": saida,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "cookies": cookies_file if cookies_file and os.path.exists(cookies_file) else None,
        "merge_output_format": "mp4",
        "format": "bestvideo+bestaudio/best",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            titulo = info.get("title", "Arquivo sem título")
            print(f"[✅] Download concluído: {titulo}")
            return titulo
    except Exception as e:
        print(f"[❌] Erro ao baixar {url}: {e}")
        return None


# ======================================================
# 🌐 3. API FastAPI (Render)
# ======================================================

app = FastAPI()

@app.get("/")
def home():
    return {"ok": True, "mensagem": "Bot universal online 🚀"}

@app.head("/health")
def health_check():
    return {"status": "alive"}

@app.post("/baixar")
async def baixar(request: Request):
    data = await request.json()
    url = data.get("url")
    if not url:
        return {"erro": "URL não fornecida"}

    titulo = baixar_midia(url)
    if titulo:
        return {"ok": True, "mensagem": f"Download concluído: {titulo}"}
    else:
        return {"ok": False, "mensagem": "Erro ao baixar o conteúdo."}


# ======================================================
# 🚀 4. INICIALIZAÇÃO (Render)
# ======================================================

if __name__ == "__main__":
    print("[SERVIDOR] Iniciando FastAPI no Render...")
    uvicorn.run(app, host="0.0.0.0", port=10000)
