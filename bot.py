# Jet TikTokShop Bot - Arquitetura C
# PTB20 Webhook + Integração Asaas (sem Flask)

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import yt_dlp
import requests
import os
import json
import asyncio
import traceback
from datetime import datetime, date
from pathlib import Path


# -------------------------
# CONFIG
# -------------------------
TOKEN = os.environ.get("BOT_TOKEN")
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

PORT = int(os.environ.get("PORT", 10000))

ARQUIVO_CONTADOR = "downloads.json"
ARQUIVO_PREMIUM = "premium.json"

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

# Criar cookies se vierem pelo Render
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])


# -------------------------
# JSON UTILS
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
USUARIOS_PREMIUM.add(ADMIN_ID)
save_premium(USUARIOS_PREMIUM)


# -------------------------
# CHECK PAGAMENTOS ASAAS
# -------------------------
def verificar_pagamentos_asaas():
    """
    Busca pagamentos confirmados no Asaas e atualiza a lista Premium.
    """
    try:
        url = f"{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()

        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                uid = int(p["metadata"]["telegram_id"])
                USUARIOS_PREMIUM.add(uid)

        save_premium(USUARIOS_PREMIUM)
    except Exception as e:
        print("Erro ao verificar Asaas:", e)


# -------------------------
# LIMITE DIÁRIO
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
        "👉 Envie um link de vídeo para baixar.\n"
        "⚠️ Free: *10 vídeos por dia*\n"
        "💎 Premium: ilimitado\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def planos(update: Update, context):
    planos = [
        ("1 Mês", 9.90, "https://www.asaas.com/c/knu5vub6ejc2yyja"),
        ("3 Meses", 25.90, "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"),
        ("1 Ano", 89.90, "https://www.asaas.com/c/puto9coszhwgprqc"),
    ]

    kb = [[InlineKeyboardButton(f"💎 {d} – R$ {v}", url=u)] for d, v, u in planos]

    await update.message.reply_text(
        "💎 Planos Premium:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


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

    # Premium automático
    verificar_pagamentos_asaas()

    # Limite diário
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
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, lambda: run(url))

        with open(file_path, "rb") as f:
            await update.message.reply_video(f, caption="✅ Seu vídeo está aqui!")

        os.remove(file_path)

        if uid not in USUARIOS_PREMIUM:
            novo = incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {novo}/{LIMITE_DIARIO}")

    except Exception as e:
        print(traceback.format_exc())
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")


# -------------------------
# MAIN (WEBHOOK NATIVO)
# -------------------------
def main():
    # Atualiza premium automático
    verificar_pagamentos_asaas()

    app = Application.builder().token(TOKEN).build()

    async def set_commands(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Iniciar bot"),
            BotCommand("planos", "Planos premium"),
            BotCommand("duvida", "Ajuda"),
            BotCommand("meuid", "Mostrar ID"),
        ])

    app.post_init = set_commands

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    # Webhook nativo
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/webhook"
    )


if __name__ == "__main__":
    main()
