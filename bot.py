import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import yt_dlp

# -----------------------------
# CONFIGURAÇÕES
# -----------------------------
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_PATH = f"/{TOKEN}/"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"

COOKIES_DIR = "cookies"  # pasta onde estão os cookies
YOUTUBE_COOKIES = os.path.join(COOKIES_DIR, "youtube.txt")
INSTAGRAM_COOKIES = os.path.join(COOKIES_DIR, "instagram.txt")
TIKTOK_COOKIES = os.path.join(COOKIES_DIR, "tiktok.txt")

# -----------------------------
# INICIALIZAÇÃO DO BOT
# -----------------------------
app = FastAPI()
bot = Bot(token=TOKEN)

application = ApplicationBuilder().token(TOKEN).build()

# -----------------------------
# FUNÇÕES DE DOWNLOAD
# -----------------------------
async def download_youtube(url: str):
    ydl_opts = {
        "cookiefile": YOUTUBE_COOKIES,
        "outtmpl": "/tmp/%(title)s.%(ext)s",
    }
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))

async def download_instagram(url: str):
    ydl_opts = {
        "cookiefile": INSTAGRAM_COOKIES,
        "outtmpl": "/tmp/%(title)s.%(ext)s",
    }
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))

async def download_tiktok(url: str):
    ydl_opts = {
        "cookiefile": TIKTOK_COOKIES,
        "outtmpl": "/tmp/%(title)s.%(ext)s",
    }
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))

# -----------------------------
# HANDLERS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot ativo! Envie o link de YouTube, Instagram ou TikTok.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    msg = await update.message.reply_text("⏳ Processando...")

    try:
        if "youtube.com" in url or "youtu.be" in url:
            info = await download_youtube(url)
        elif "instagram.com" in url:
            info = await download_instagram(url)
        elif "tiktok.com" in url:
            info = await download_tiktok(url)
        else:
            await msg.edit_text("❌ URL não reconhecida.")
            return

        file_path = info.get("requested_downloads")[0]["filepath"] if info.get("requested_downloads") else None
        if file_path:
            await update.message.reply_document(document=open(file_path, "rb"))
            await msg.delete()
        else:
            await msg.edit_text("❌ Falha ao baixar o vídeo.")

    except Exception as e:
        await msg.edit_text(f"❌ Erro: {e}")

# -----------------------------
# REGISTRO DE HANDLERS
# -----------------------------
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# -----------------------------
# WEBHOOK FASTAPI
# -----------------------------
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update = Update.de_json(await request.json(), bot)
    await application.update_queue.put(update)
    return {"ok": True}

# -----------------------------
# START DO BOT
# -----------------------------
@app.on_event("startup")
async def startup():
    # Configurar webhook no Telegram
    await bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook configurado em: {WEBHOOK_URL}")
