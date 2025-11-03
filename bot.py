import os
import asyncio
import threading
import nest_asyncio
from fastapi import FastAPI
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, filters
from telegram import InputFile
from yt_dlp import YoutubeDL

# =======================
# CONFIGURAÇÕES
# =======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
COOKIES_INSTAGRAM = os.getenv("COOKIES_INSTAGRAM")
COOKIES_YOUTUBE = os.getenv("COOKIES_YOUTUBE")
COOKIES_TIKTOK = os.getenv("COOKIES_TIKTOK")

DOWNLOAD_FOLDER = "/tmp"

# =======================
# FASTAPI
# =======================
app = FastAPI()

@app.get("/")
async def root():
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "running"}

# =======================
# FUNÇÕES DE DOWNLOAD
# =======================
def baixar_instagram(url):
    ydl_opts = {
        "cookiefile": COOKIES_INSTAGRAM,
        "outtmpl": os.path.join(DOWNLOAD_FOLDER, "instagram_%(id)s.%(ext)s")
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename if os.path.exists(filename) else None

def baixar_youtube(url):
    ydl_opts = {
        "cookiefile": COOKIES_YOUTUBE,
        "outtmpl": os.path.join(DOWNLOAD_FOLDER, "youtube_%(id)s.%(ext)s")
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename if os.path.exists(filename) else None

def baixar_tiktok(url):
    ydl_opts = {
        "cookiefile": COOKIES_TIKTOK,
        "outtmpl": os.path.join(DOWNLOAD_FOLDER, "tiktok_%(id)s.%(ext)s")
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename if os.path.exists(filename) else None

# =======================
# HANDLERS DO BOT
# =======================
async def start_command(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot ativo! Envie /baixar <link> para baixar vídeos.")

async def baixar_command(update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Use: /baixar <link>")
        return

    url = context.args[0]
    await update.message.reply_text("⏳ Iniciando download...")

    try:
        if "instagram.com" in url:
            arquivo = baixar_instagram(url)
        elif "youtube.com" in url or "youtu.be" in url:
            arquivo = baixar_youtube(url)
        elif "tiktok.com" in url:
            arquivo = baixar_tiktok(url)
        else:
            await update.message.reply_text("❌ URL não suportada.")
            return

        if arquivo:
            # Envia o vídeo pelo Telegram
            with open(arquivo, "rb") as f:
                await update.message.reply_video(video=InputFile(f, filename=os.path.basename(arquivo)))
            await update.message.reply_text("✅ Download e envio concluído!")
            os.remove(arquivo)  # Remove arquivo temporário
        else:
            await update.message.reply_text("❌ Falha ao baixar o vídeo.")

    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")

# =======================
# INICIALIZAÇÃO DO BOT
# =======================
def run_bot():
    nest_asyncio.apply()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("baixar", baixar_command))

    # Iniciar polling
    application.run_polling()

bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

# =======================
# RODAR FASTAPI
# =======================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
