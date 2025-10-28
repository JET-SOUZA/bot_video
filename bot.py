import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
import yt_dlp
import os
import requests

# ----------------------------
# CONFIGURAÇÕES
# ----------------------------
TOKEN = "8249697837:AAGfvejL5PT9w8sSPMZnIwErh0jX-XMpAPE"
ADMIN_ID = 5593153639

ASAAS_API_KEY = "$aact_prod_000MzkwODA2MWY2OGM3MWRlMDU2NWM3MzJlNzZmNGZhZGY6OjQxNTY4M2IzLTU1M2UtNGEyNS05ODQ5LTUzM2Q1OTBiYzdiZTo6JGFhY2hfNGU1ZmE3OGEtMzliNS00OTZlLWFmMGMtNDMzN2VlMzM1Yjlh"
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

WEBHOOK_URL = "https://bot-video-mgli.onrender.com/webhook_telegram"
MAX_VIDEO_SIZE_MB = 50  # máximo permitido para enviar pelo Telegram

# ----------------------------
# FLASK
# ----------------------------
flask_app = Flask(__name__)

# ----------------------------
# TELEGRAM BOT
# ----------------------------
bot_app = ApplicationBuilder().token(TOKEN).build()

# ----------------------------
# FUNÇÕES DO BOT
# ----------------------------
async def start(update: Update, context):
    await update.message.reply_text(
        "Olá! Envie um link de vídeo do YouTube, TikTok ou Reels para baixar."
    )

async def baixar_video(update: Update, context):
    url = update.message.text
    msg = await update.message.reply_text("Baixando vídeo... ⏳")

    try:
        ydl_opts = {
            'format': 'mp4',
            'outtmpl': '/tmp/%(id)s.%(ext)s'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)

        # Verifica tamanho do arquivo
        size_mb = os.path.getsize(video_path) / (1024 * 1024)
        if size_mb > MAX_VIDEO_SIZE_MB:
            await update.message.reply_text(
                f"O vídeo é muito grande ({size_mb:.2f} MB). Limite: {MAX_VIDEO_SIZE_MB} MB."
            )
            os.remove(video_path)
        else:
            # envia vídeo
            with open(video_path, "rb") as f:
                await update.message.reply_video(f)
            os.remove(video_path)

        await msg.delete()

    except Exception as e:
        await update.message.reply_text(f"Erro ao baixar vídeo: {e}")
        await msg.delete()

# ----------------------------
# ASAAS (EXEMPLO)
# ----------------------------
def criar_cobranca(valor: float, cliente_id: str, descricao: str):
    url = f"{ASAAS_BASE_URL}/payments"
    headers = {
        "access_token": ASAAS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "customer": cliente_id,
        "billingType": "BOLETO",
        "dueDate": "2025-11-10",
        "value": valor,
        "description": descricao
    }
    response = requests.post(url, json=data, headers=headers)
    return response.json()

# ----------------------------
# ADICIONA HANDLERS
# ----------------------------
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

# ----------------------------
# WEBHOOK FLASK
# ----------------------------
@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot_app.bot)
    bot_app.update_queue.put_nowait(update)
    return "OK", 200

# ----------------------------
# INICIALIZAÇÃO DO BOT
# ----------------------------
async def main():
    await bot_app.bot.set_webhook(WEBHOOK_URL)
    await bot_app.initialize()
    await bot_app.start()
    print("🤖 Bot iniciado e pronto!")

    # Mantém o bot rodando para processar updates da fila
    await bot_app.updater.start_polling()

# ----------------------------
# RODA FLASK + BOT
# ----------------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    flask_app.run(host="0.0.0.0", port=10000)
