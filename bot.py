import asyncio
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
import yt_dlp

TOKEN = "SEU_TOKEN_AQUI"
WEBHOOK_URL = "https://bot-video-mgli.onrender.com/webhook_telegram"

# ----------------------------
# Flask
# ----------------------------
flask_app = Flask(__name__)

# ----------------------------
# Bot
# ----------------------------
bot_app = ApplicationBuilder().token(TOKEN).build()

# ----------------------------
# Handlers
# ----------------------------
async def start(update: Update, context):
    await update.message.reply_text("Olá! Envie um link de vídeo para baixar.")

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

        # envia vídeo
        with open(video_path, "rb") as f:
            await update.message.reply_video(f)
        await msg.delete()
    except Exception as e:
        await update.message.reply_text(f"Erro ao baixar vídeo: {e}")
        await msg.delete()

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

# ----------------------------
# Webhook Flask
# ----------------------------
@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot_app.bot)
    bot_app.update_queue.put_nowait(update)
    return "OK", 200

# ----------------------------
# Inicialização do bot
# ----------------------------
async def main():
    # Define webhook
    await bot_app.bot.set_webhook(WEBHOOK_URL)

    # Inicializa o bot
    await bot_app.initialize()
    await bot_app.start()
    print("🤖 Bot iniciado e pronto!")

    # Mantém o bot rodando
    await bot_app.updater.start_polling()  # necessário para processar updates da fila

# ----------------------------
# Roda o Flask + Bot
# ----------------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    flask_app.run(host="0.0.0.0", port=10000)
