import os
import asyncio
import base64
import subprocess
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ============================================================
# 🔧 DECODIFICAÇÃO DE COOKIES BASE64
# ============================================================

def decode_cookie(var_name, file_name):
    """
    Lê a variável Base64, decodifica e salva localmente.
    """
    b64 = os.getenv(var_name)
    if not b64:
        print(f"⚠️ Variável {var_name} não definida.")
        return None
    try:
        decoded = base64.b64decode(b64).decode("utf-8")
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(decoded)
        print(f"✅ {var_name} decodificado e salvo em {file_name}")
        return file_name
    except Exception as e:
        print(f"❌ Erro ao decodificar {var_name}: {e}")
        return None


cookies_shopee = decode_cookie("COOKIES_SHOPEE_B64", "cookies_shopee.txt")
cookies_instagram = decode_cookie("COOKIES_IG_B64", "cookies_instagram.txt")

# ============================================================
# 🤖 CONFIGURAÇÃO DO TELEGRAM
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Ex: https://seu-bot.onrender.com/webhook

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN não definido nas variáveis de ambiente!")
if not WEBHOOK_URL:
    raise ValueError("❌ WEBHOOK_URL não definido nas variáveis de ambiente!")

application = Application.builder().token(BOT_TOKEN).build()
app = Flask(__name__)

# ============================================================
# 💬 FUNÇÕES DO BOT
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Olá! Envie um link de vídeo da Shopee, Instagram ou TikTok!")

async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("❌ Envie um link válido.")
        return

    await update.message.reply_text("⏳ Baixando vídeo, aguarde...")

    try:
        os.makedirs("downloads", exist_ok=True)
        command = ["yt-dlp", "-o", "downloads/%(title)s.%(ext)s", url]

        # Adiciona cookies se necessário
        if "shopee" in url and cookies_shopee:
            command += ["--cookies", cookies_shopee]
        elif "instagram" in url and cookies_instagram:
            command += ["--cookies", cookies_instagram]

        process = subprocess.run(command, capture_output=True, text=True)

        if process.returncode == 0:
            await update.message.reply_text("✅ Download concluído com sucesso!")
        else:
            erro = process.stderr or process.stdout
            await update.message.reply_text(f"⚠️ Erro ao baixar vídeo:\n{erro[:500]}")

    except Exception as e:
        await update.message.reply_text(f"❌ Ocorreu um erro: {e}")

# ============================================================
# 🔗 HANDLERS
# ============================================================

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

# ============================================================
# 🌐 FLASK ENDPOINTS
# ============================================================

@app.route("/")
def home():
    return {"ok": True, "status": "bot online"}

@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/webhook", methods=["POST"])
async def telegram_webhook():
    """Recebe mensagens do Telegram via Webhook"""
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return {"ok": True}

# ============================================================
# 🚀 INICIALIZAÇÃO DO WEBHOOK
# ============================================================

async def setup_webhook():
    print("🧩 Configurando webhook...")
    await application.bot.delete_webhook()
    await application.bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook configurado com sucesso: {WEBHOOK_URL}")

if __name__ == "__main__":
    asyncio.run(setup_webhook())
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Servidor iniciado na porta {port}")
    app.run(host="0.0.0.0", port=port)
