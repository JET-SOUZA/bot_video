import os
import yt_dlp
from fastapi import FastAPI
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import nest_asyncio
import asyncio

nest_asyncio.apply()

# -----------------------------
# Configurações do Bot
# -----------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(token=TELEGRAM_TOKEN)

app = FastAPI()

# -----------------------------
# Função para salvar cookies em arquivo
# -----------------------------
def salvar_cookies(nome_variavel_env, arquivo_destino):
    conteudo = os.getenv(nome_variavel_env)
    if conteudo:
        with open(arquivo_destino, "w") as f:
            f.write(conteudo)
        print(f"[OK] Cookie salvo: {nome_variavel_env}")
    else:
        print(f"[⚠️] Variável {nome_variavel_env} não encontrada.")

# Salva cookies de todas as plataformas
salvar_cookies("COOKIES_INSTAGRAM", "instagram_cookies.txt")
salvar_cookies("COOKIES_YOUTUBE", "youtube_cookies.txt")
salvar_cookies("COOKIES_TIKTOK", "tiktok_cookies.txt")
# Twitter opcional
# salvar_cookies("COOKIES_TWITTER", "twitter_cookies.txt")

# -----------------------------
# Função para download de vídeo
# -----------------------------
def baixar_video(url, plataforma="youtube"):
    ydl_opts = {
        "outtmpl": "downloads/%(title)s.%(ext)s",
        "noplaylist": True,
        "quiet": True,
    }

    # Configura cookies dependendo da plataforma
    if plataforma == "youtube":
        ydl_opts["cookiefile"] = "youtube_cookies.txt"
    elif plataforma == "instagram":
        ydl_opts["cookiefile"] = "instagram_cookies.txt"
    elif plataforma == "tiktok":
        ydl_opts["cookiefile"] = "tiktok_cookies.txt"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info.get("title", "video")
    except Exception as e:
        print(f"[ERRO] Não foi possível baixar o vídeo: {e}")
        return None

# -----------------------------
# Comandos do Telegram
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot ativo! Envie o link do vídeo do YouTube, Instagram ou TikTok.")

async def baixar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "instagram.com" in url:
        plataforma = "instagram"
    elif "youtube.com" in url or "youtu.be" in url:
        plataforma = "youtube"
    elif "tiktok.com" in url:
        plataforma = "tiktok"
    else:
        await update.message.reply_text("❌ Plataforma não suportada.")
        return

    await update.message.reply_text("⏳ Baixando vídeo...")
    titulo = baixar_video(url, plataforma)
    if titulo:
        await update.message.reply_text(f"✅ Download concluído: {titulo}")
    else:
        await update.message.reply_text("❌ Falha ao baixar o vídeo.")

# -----------------------------
# Iniciando o bot do Telegram
# -----------------------------
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar))

# Executa o bot em background
asyncio.create_task(application.run_polling())

# -----------------------------
# Rota FastAPI apenas para healthcheck
# -----------------------------
@app.get("/")
def root():
    return {"ok": True}
