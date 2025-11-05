import os
import json
import base64
import asyncio
import logging
import aiofiles
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import yt_dlp
import nest_asyncio

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Variáveis de ambiente ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/") + "/webhook"

COOKIES_IG_B64 = os.getenv("COOKIES_IG_B64")
COOKIES_SHOPEE_B64 = os.getenv("COOKIES_SHOPEE_B64")

# === Decodifica cookies Base64 e salva ===
def salvar_cookies(nome, conteudo_b64):
    if not conteudo_b64:
        logger.warning(f"⚠️ Nenhum cookie encontrado para {nome}.")
        return None
    try:
        decoded = base64.b64decode(conteudo_b64).decode("utf-8")
        path = f"/opt/render/project/src/{nome}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(decoded)
        logger.info(f"✅ Cookies de {nome} salvos com sucesso!")
        return path
    except Exception as e:
        logger.error(f"Erro ao salvar cookies {nome}: {e}")
        return None

COOKIES_IG_PATH = salvar_cookies("cookies_instagram", COOKIES_IG_B64)
COOKIES_SHOPEE_PATH = salvar_cookies("cookies_shopee", COOKIES_SHOPEE_B64)

# === Flask ===
flask_app = Flask(__name__)

# === Telegram Bot ===
application = ApplicationBuilder().token(BOT_TOKEN).build()

# === Funções principais ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot ativo! Envie um link do Instagram ou Shopee.")

async def baixar_video(url: str, origem: str):
    logger.info(f"Baixando vídeo de {origem}: {url}")
    cookies_path = COOKIES_IG_PATH if origem == "instagram" else COOKIES_SHOPEE_PATH
    output_dir = "/opt/render/project/src/downloads"
    os.makedirs(output_dir, exist_ok=True)
    opts = {
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "cookies": cookies_path,
        "format": "best",
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename if os.path.exists(filename) else None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "instagram.com" in text:
        origem = "instagram"
    elif "shopee.com" in text:
        origem = "shopee"
    else:
        await update.message.reply_text("Envie um link válido do Instagram ou Shopee.")
        return

    await update.message.reply_text("⬇️ Baixando vídeo, aguarde...")

    try:
        file_path = await baixar_video(text, origem)
        if file_path:
            async with aiofiles.open(file_path, "rb") as f:
                await update.message.reply_video(f)
        else:
            await update.message.reply_text("❌ Erro: vídeo não encontrado após download.")
    except Exception as e:
        logger.error(f"Erro ao baixar {origem}: {e}")
        await update.message.reply_text(f"Erro ao baixar: {e}")

# === Handlers ===
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === Webhook Flask route ===
@flask_app.route("/webhook", methods=["POST"])
async def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        if not application.initialized:
            await application.initialize()
            await application.start()
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
    return jsonify({"ok": True})

@flask_app.route("/health", methods=["HEAD", "GET"])
def health():
    return jsonify({"ok": True})

# === Inicialização ===
async def main():
    logger.info("🚀 Iniciando bot...")
    await application.initialize()
    await application.bot.set_webhook(url=WEBHOOK_URL)
    await application.start()
    logger.info("🤖 Bot ativo e pronto para Webhook...")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    flask_app.run(host="0.0.0.0", port=10000)
