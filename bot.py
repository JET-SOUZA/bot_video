import os
import base64
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import aiofiles

# === Configurações básicas ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
PORT = int(os.getenv("PORT", 10000))

# === Cookies (base64) ===
def salvar_cookies(nome, valor_b64):
    if not valor_b64:
        return None
    path = f"{nome}.txt"
    try:
        data = base64.b64decode(valor_b64).decode("utf-8")
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        print(f"✅ Cookies salvos em {path}")
        return path
    except Exception as e:
        print(f"❌ Erro ao decodificar cookies {nome}: {e}")
        return None

COOKIES_IG = salvar_cookies("cookies_instagram", os.getenv("COOKIES_IG_B64"))
COOKIES_SHOPEE = salvar_cookies("cookies_shopee", os.getenv("COOKIES_SHOPEE_B64"))

# === Inicializa bot + Flask ===
app_flask = Flask(__name__)
app = Application.builder().token(BOT_TOKEN).build()

# === Função principal de download ===
async def baixar_video(url: str, cookies_path: str | None):
    print(f"⬇️ Iniciando download: {url}")
    os.makedirs("downloads", exist_ok=True)

    ydl_opts = {
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
        "cookiefile": cookies_path,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        print(f"❌ Erro no yt_dlp: {e}")
        return None

# === Manipulador de mensagens ===
async def receber_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    if "shopee" in url:
        cookies_path = COOKIES_SHOPEE
    elif "instagram" in url:
        cookies_path = COOKIES_IG
    else:
        await update.message.reply_text("❌ Envie um link válido do Instagram ou Shopee.")
        return

    await update.message.reply_text("⏳ Baixando vídeo, aguarde...")

    try:
        file_path = await baixar_video(url, cookies_path)
        if file_path and os.path.exists(file_path):
            async with aiofiles.open(file_path, "rb") as f:
                data = await f.read()
            await update.message.reply_video(data, caption="✅ Aqui está seu vídeo!")
            os.remove(file_path)
        else:
            await update.message.reply_text("❌ Erro ao baixar: arquivo não encontrado.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")
        print(f"Erro ao enviar vídeo: {e}")

# === Comandos ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Envie um link do Instagram ou Shopee para baixar o vídeo.")

# === Flask Webhook ===
@app_flask.route("/")
def home():
    return "Bot ativo 🚀"

@app_flask.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    asyncio.run(app.process_update(update))
    return "ok", 200

# === Função principal ===
async def configurar_webhook():
    try:
        await app.bot.delete_webhook()
        await app.bot.set_webhook(WEBHOOK_URL)
        print(f"✅ Webhook configurado: {WEBHOOK_URL}")
    except Exception as e:
        print(f"❌ Erro ao configurar webhook: {e}")

def main():
    print("🤖 Bot ativo e pronto para Webhook...")
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_mensagem))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(configurar_webhook())
    app_flask.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
