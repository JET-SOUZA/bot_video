import os
import asyncio
import yt_dlp
from fastapi import FastAPI
import nest_asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import uvicorn

# Corrige event loop do Render
nest_asyncio.apply()

# ==========================
# 🔹 CONFIGURAÇÕES GERAIS
# ==========================

TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.getenv("PORT", 10000))

os.makedirs("downloads", exist_ok=True)
os.makedirs("cookies", exist_ok=True)

# ==========================
# 🔹 SALVAR COOKIES
# ==========================

def salvar_cookies():
    cookies_envs = {
        "COOKIES_INSTAGRAM": "instagram.txt",
        "COOKIES_YOUTUBE": "youtube.txt",
        "COOKIES_TIKTOK": "tiktok.txt",
        "COOKIES_TWITTER": "twitter.txt"
    }

    for env, filename in cookies_envs.items():
        valor = os.getenv(env)
        if valor:
            path = os.path.join("cookies", filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(valor)
            print(f"[OK] Cookie salvo: {env}")
        else:
            print(f"[⚠️] Variável {env} não encontrada.")

salvar_cookies()

# ==========================
# 🔹 FASTAPI SERVIDOR
# ==========================

app = FastAPI()

@app.get("/")
async def home():
    return {"ok": True, "message": "Servidor e bot rodando corretamente 🚀"}

@app.get("/health")
async def health():
    return {"status": "ok"}

# ==========================
# 🔹 TELEGRAM BOT
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Envie um link de vídeo para baixar.")

async def baixar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.reply_text("⏳ Baixando, aguarde...")

    output_path = "downloads/%(title)s.%(ext)s"
    cookies = None

    if "instagram.com" in url:
        cookies = "cookies/instagram.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        cookies = "cookies/youtube.txt"
    elif "tiktok.com" in url:
        cookies = "cookies/tiktok.txt"
    elif "x.com" in url or "twitter.com" in url:
        cookies = "cookies/twitter.txt"

    ydl_opts = {
        "outtmpl": output_path,
        "quiet": True,
        "cookiefile": cookies if cookies else None,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            nome = ydl.prepare_filename(info)
        if os.path.exists(nome):
            await update.message.reply_document(document=open(nome, "rb"))
            os.remove(nome)
        else:
            await update.message.reply_text("❌ Erro: arquivo não encontrado.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro: {str(e)}")

async def iniciar_bot():
    print("🤖 Iniciando bot do Telegram...")
    app_tg = ApplicationBuilder().token(TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar))
    await app_tg.run_polling()

# ==========================
# 🔹 INICIALIZAÇÃO GERAL
# ==========================

async def main():
    # Inicia o bot e o servidor FastAPI em paralelo
    bot_task = asyncio.create_task(iniciar_bot())
    config = uvicorn.Config(app=app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    api_task = asyncio.create_task(server.serve())

    await asyncio.gather(bot_task, api_task)

if __name__ == "__main__":
    asyncio.run(main())
