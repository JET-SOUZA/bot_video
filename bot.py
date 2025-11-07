# Jet TikTokShop Bot - Render Compatible (Flask HTTP Server + PTB20)

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    BotCommand
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import yt_dlp
import os
import json
import aiohttp
import asyncio
import traceback
from datetime import date, datetime
from pathlib import Path
from flask import Flask, request


# -------------------------
# CONFIGURAÇÕES
# -------------------------
TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 5000))

ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

ARQUIVO_CONTADOR = "downloads.json"
ARQUIVO_PREMIUM = "premium.json"


SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

# Criar cookies se vierem via variável de ambiente
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])


# -------------------------
# JSON HELPERS
# -------------------------
def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


# -------------------------
# PREMIUM
# -------------------------
def load_premium():
    data = load_json(ARQUIVO_PREMIUM)
    return set(map(int, data.get("premium_users", [])))

def save_premium(users):
    save_json(ARQUIVO_PREMIUM, {"premium_users": list(users)})


USUARIOS_PREMIUM = load_premium()
USUARIOS_PREMIUM.update({ADMIN_ID, 0, 0, 0})
save_premium(USUARIOS_PREMIUM)


# -------------------------
# LIMITES
# -------------------------
def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())

    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)

    return data[str(uid)]["downloads"]

def incrementar_download(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())

    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        data[str(uid)]["downloads"] += 1

    save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]


# -------------------------
# COMANDOS
# -------------------------
async def start(update: Update, context):
    msg = (
        "🎬 *Bem-vindo ao Jet TikTokShop Bot!*\n\n"
        "👉 Envie o link do vídeo para baixar.\n"
        "⚠️ Free: *10 vídeos por dia*\n"
        "💎 Premium: ilimitado"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def planos(update: Update, context):
    planos = [
        ("1 Mês", 9.90, "https://www.asaas.com/c/knu5vub6ejc2yyja"),
        ("3 Meses", 25.90, "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"),
        ("1 Ano", 89.90, "https://www.asaas.com/c/puto9coszhwgprqc"),
    ]

    kb = [[InlineKeyboardButton(f"💎 {d} - R$ {v}", url=u)] for d, v, u in planos]
    await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))


async def duvida(update: Update, context):
    await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")


async def meuid(update: Update, context):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")


# -------------------------
# DOWNLOAD
# -------------------------
async def baixar_video(update: Update, context):
    url = update.message.text.strip()
    uid = update.message.from_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    if uid not in USUARIOS_PREMIUM:
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    await update.message.reply_text("⏳ Baixando...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        ydl_opts = {
            "outtmpl": output,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
        }

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                data = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(data)

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, lambda: run(url))

        with open(file_path, "rb") as f:
            await update.message.reply_video(f, caption="✅ Aqui está seu vídeo!")

        os.remove(file_path)

        if uid not in USUARIOS_PREMIUM:
            new = incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {new}/{LIMITE_DIARIO}")

    except Exception as e:
        print(traceback.format_exc())
        await update.message.reply_text(f"❌ Erro: {e}")


# -------------------------
# FLASK (WEBHOOK)
# -------------------------
flask_app = Flask(__name__)


@flask_app.route("/health")
def health():
    return "OK", 200


@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    asyncio.run(bot_app.process_update(update))
    return "OK", 200


# -------------------------
# MAIN
# -------------------------
def main():
    global bot_app
    bot_app = ApplicationBuilder().token(TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("planos", planos))
    bot_app.add_handler(CommandHandler("duvida", duvida))
    bot_app.add_handler(CommandHandler("meuid", meuid))

    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    # Inicializa bot — sem webhook interno!!
    asyncio.run(bot_app.initialize())
    asyncio.run(bot_app.start())

    print("✅ Bot iniciado e aguardando webhooks...")

    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
