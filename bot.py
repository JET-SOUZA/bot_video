import logging
import os
import yt_dlp
import aiofiles
import asyncio
import nest_asyncio

from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

nest_asyncio.apply()

# === CONFIGURAÇÕES ===
TOKEN = os.getenv("TELEGRAM_TOKEN", "SEU_TOKEN_AQUI")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "")  # Ex: https://jet-bot.onrender.com

# === LOGS ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === APP TELEGRAM ===
application = Application.builder().token(TOKEN).build()
bot = Bot(TOKEN)

# === APP FLASK ===
flask_app = Flask(__name__)


# === COMANDO /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Envie um link do Instagram (post, reel ou story) para baixar o vídeo.")


# === FUNÇÃO DE DOWNLOAD ===
async def download_instagram_video(url: str) -> str:
    logger.info(f"Baixando mídia de: {url}")

    ydl_opts = {
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "format": "best[ext=mp4]",
        "quiet": True,
        "nocheckcertificate": True,
    }

    os.makedirs("downloads", exist_ok=True)

    loop = asyncio.get_event_loop()

    try:
        def run_yt_dlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(result)
                return filename

        filename = await loop.run_in_executor(None, run_yt_dlp)

        if not os.path.exists(filename):
            raise FileNotFoundError(f"Arquivo não encontrado após o download: {filename}")

        return filename

    except Exception as e:
        logger.error(f"Erro ao baixar: {e}")
        raise


# === TRATAR LINKS ENVIADOS ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text.strip()

    if not ("instagram.com" in message or "instagr.am" in message):
        await update.message.reply_text("❌ Envie um link válido do Instagram.")
        return

    msg = await update.message.reply_text("📥 Baixando o vídeo, aguarde...")

    try:
        filepath = await download_instagram_video(message)
        async with aiofiles.open(filepath, "rb") as f:
            await update.message.reply_video(video=await f.read(), caption="✅ Download concluído!")
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"⚠️ Erro ao baixar: {e}")


# === REGISTRA HANDLERS ===
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


# === FLASK WEBHOOK ===
@flask_app.route("/")
def index():
    return jsonify({"ok": True, "message": "Bot ativo"})


@flask_app.route("/webhook", methods=["POST"])
async def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        try:
            await application.initialize()
            await application.start()
        except RuntimeError:
            pass
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
    return jsonify({"ok": True})


# === INICIAR SERVIDOR ===
if __name__ == "__main__":
    async def run():
        if WEBHOOK_URL:
            webhook_url = f"{WEBHOOK_URL}/webhook"
            await bot.set_webhook(webhook_url)
            logger.info(f"🌐 Webhook definido para: {webhook_url}")
        else:
            logger.warning("⚠️ Variável RENDER_EXTERNAL_URL não configurada!")
        flask_app.run(host="0.0.0.0", port=PORT)

    asyncio.run(run())
