# bot_render.py
import os
import json
import asyncio
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path

import aiohttp
import yt_dlp
from flask import Flask, request
from telegram import Update, BotCommand, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ==========================
# CONFIGURAÇÕES
# ==========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # ex: https://bot-video-mgli.onrender.com/webhook_telegram
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

LIMITE_DIARIO = 10
MAX_VIDEO_MB_SEND = 50

# ==========================
# FLASK APP
# ==========================
flask_app = Flask(__name__)

# ==========================
# UTILS
# ==========================
def carregar_json(caminho: Path):
    if caminho.exists():
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def salvar_json(caminho: Path, dados: dict):
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"

def carregar_contador():
    return carregar_json(ARQUIVO_CONTADOR)

def salvar_contador(dados: dict):
    salvar_json(ARQUIVO_CONTADOR, dados)

# ==========================
# HANDLERS
# ==========================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "🎬 *Bem-vindo ao bot!* Envie um link do vídeo para baixar."
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def meuid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu Telegram ID: `{update.effective_user.id}`", parse_mode="Markdown")

async def baixar_video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.message.from_user.id

    if not texto.startswith("http"):
        await update.message.reply_text("❌ Envie um link válido.")
        return

    dados = carregar_contador()
    hoje = str(date.today())
    if str(user_id) not in dados or dados[str(user_id)].get("data") != hoje:
        dados[str(user_id)] = {"data": hoje, "downloads": 0}

    if dados[str(user_id)]["downloads"] >= LIMITE_DIARIO:
        await update.message.reply_text("⚠️ Limite diário atingido.")
        return

    status_msg = await update.message.reply_text("⏳ Preparando download...")
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        out_template = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")
        ydl_opts = {
            "outtmpl": out_template,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "ignoreerrors": True,
        }
        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))

        candidato = ydl_obj.prepare_filename(info)
        tamanho_mb = Path(candidato).stat().st_size / (1024 * 1024)
        with open(candidato, "rb") as f:
            if tamanho_mb > MAX_VIDEO_MB_SEND:
                await update.message.reply_document(f, caption="✅ Aqui está seu vídeo (documento).")
            else:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo em alta qualidade!")

        dados[str(user_id)]["downloads"] += 1
        salvar_contador(dados)

        await update.message.reply_text(
            f"📊 Uso diário: *{dados[str(user_id)]['downloads']}/{LIMITE_DIARIO}*", parse_mode="Markdown"
        )
        Path(candidato).unlink(missing_ok=True)
        await status_msg.delete()
    except Exception as e:
        print(traceback.format_exc())
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# ==========================
# FLASK WEBHOOK
# ==========================
bot_app = None  # Application global

@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    global bot_app
    if bot_app is None:
        return "Bot ainda não inicializado", 503
    data = request.get_json(force=True)
    update = Update.de_json(data, bot_app.bot)
    bot_app.update_queue.put_nowait(update)
    return "OK", 200

@flask_app.route("/", methods=["GET"])
def index():
    return "🤖 Bot ativo!", 200

# ==========================
# MAIN
# ==========================
async def start_bot():
    global bot_app
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    bot_app.add_handler(CommandHandler("start", start_handler))
    bot_app.add_handler(CommandHandler("meuid", meuid_handler))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video_handler))

    # Comandos
    async def _post_init(a):
        await a.bot.set_my_commands([
            BotCommand("start", "Iniciar"),
            BotCommand("meuid", "Ver seu ID"),
        ])
    bot_app.post_init = _post_init

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.bot.set_webhook(WEBHOOK_URL)
    print("✅ Webhook ativo em:", WEBHOOK_URL)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    from threading import Thread

    # Rodar Flask em thread separada
    Thread(target=lambda: flask_app.run(host="0.0.0.0", port=port), daemon=True).start()

    # Rodar bot
    asyncio.run(start_bot())
