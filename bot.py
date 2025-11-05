import os
import asyncio
import base64
import logging
import aiohttp
import aiofiles
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# === CONFIGURAÇÕES ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "https://seuapp.onrender.com")
COOKIES_B64 = os.getenv("COOKIES_IG_B64")

if not TOKEN:
    raise ValueError("❌ Variável TELEGRAM_TOKEN não configurada.")
if not COOKIES_B64:
    raise ValueError("❌ Variável COOKIES_IG_B64 não configurada.")

# Caminho dos downloads
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# === CONFIGURAÇÃO DE LOG ===
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === SALVAR COOKIES DECODIFICADOS ===
COOKIES_PATH = os.path.join(DOWNLOAD_DIR, "cookies_instagram.txt")
with open(COOKIES_PATH, "wb") as f:
    f.write(base64.b64decode(COOKIES_B64))
logger.info(f"✅ Cookies salvos em {COOKIES_PATH}")

# === FUNÇÕES ===

async def baixar_instagram(url: str) -> str:
    """Baixa vídeos do Instagram (post ou story)."""
    import yt_dlp

    output_path = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "best",
        "outtmpl": output_path,
        "quiet": True,
        "cookiefile": COOKIES_PATH,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id")
            ext = info.get("ext", "mp4")
            file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

            # Se o arquivo vier com ".NA", tenta renomear
            if not os.path.exists(file_path):
                for arquivo in os.listdir(DOWNLOAD_DIR):
                    if arquivo.startswith(video_id) and arquivo.endswith(".NA"):
                        novo_nome = f"{video_id}.mp4"
                        os.rename(os.path.join(DOWNLOAD_DIR, arquivo), os.path.join(DOWNLOAD_DIR, novo_nome))
                        file_path = os.path.join(DOWNLOAD_DIR, novo_nome)
                        break

            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

            return file_path

    except Exception as e:
        logger.error(f"Erro ao baixar vídeo: {e}")
        raise


# === HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Envie um link do Instagram para baixar o vídeo ou story!")

async def handle_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "instagram.com" not in url:
        await update.message.reply_text("⚠️ Envie um link válido do Instagram.")
        return

    await update.message.reply_text("⬇️ Baixando vídeo... aguarde.")

    try:
        file_path = await baixar_instagram(url)
        if os.path.exists(file_path):
            async with aiofiles.open(file_path, "rb") as f:
                await update.message.reply_video(video=await f.read())
            os.remove(file_path)
        else:
            await update.message.reply_text("❌ Arquivo não encontrado após o download.")
    except Exception as e:
        await update.message.reply_text(f"Erro ao baixar: {e}")
        logger.error(e)


# === FLASK APP (para WEBHOOK) ===

app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

@app.route("/webhook", methods=["POST"])
async def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return "OK", 200

@app.route("/health")
def health():
    return {"ok": True}, 200

# === SETUP FINAL ===

async def main():
    await application.bot.delete_webhook()
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"🤖 Bot ativo e pronto para Webhook em {webhook_url}")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instagram))

    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    config = Config()
    config.bind = ["0.0.0.0:10000"]
    await serve(app, config)

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
