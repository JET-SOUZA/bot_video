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

    if uid not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)

    return data[str(uid)]["downloads"]

def incrementar_download(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())

    if uid not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        data[str(uid)]["downloads"] += 1

    save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]


# -------------------------
# DOWNLOAD + SHOPEE PATCH ABSOLUTO
# -------------------------
async def baixar_video(update: Update, context):

    # ✅ INÍCIO DA FUNÇÃO
    url = update.message.text.strip()
    uid = update.message.from_user.id

    # ✅ SHOPEE PATCH ABSOLUTO — SEMPRE EXECUTA PRIMEIRO
    from urllib.parse import unquote
    import re

    original_url = url
    url = unquote(url).replace("\\/", "/").replace("\u200b", "").strip()

    # Detecta Shopee
    if "shopee.com" in url or "sv.shopee.com" in url:
        try:
            await update.message.reply_text("🔄 Resolvendo link da Shopee...")

            # Extrair share-video ID
            m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", url)

            if not m:
                try:
                    html = requests.get(url, timeout=10).text
                    m = re.search(
                        r"https://sv\.shopee\.com\.br/share-video/([A-Za-z0-9=_\-]+)", 
                        html
                    )
                except:
                    pass

            if not m:
                return await update.message.reply_text("❌ Não consegui extrair o ID do vídeo da Shopee.")

            share_id = m.group(1)

            # API v4 Shopee
            api_url = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
            data = requests.get(api_url, timeout=10).json()

            video_url = data.get("data", {}).get("video_url")
            if not video_url:
                return await update.message.reply_text("❌ A Shopee não retornou o video_url.")

            url = video_url  # ✅ Agora sim

        except Exception as e:
            return await update.message.reply_text(f"❌ Erro ao resolver Shopee: {e}")

    # ✅ VALIDADO — A PARTIR DAQUI O BOT FUNCIONA NORMALMENTE

    verificar_pagamentos_asaas()

    if uid not in USUARIOS_PREMIUM:
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Link inválido.")

    await update.message.reply_text("⏳ Baixando...")

    # -------------------------
    # DOWNLOAD VIA YT-DLP
    # -------------------------
    try:
        output = str(DOWNLOADS_DIR / f"%(id)s-{datetime.now().strftime('%H%M%S')}.%(ext)s")

        ydl_opts = {
            "outtmpl": output,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4"
        }

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        file_path = await asyncio.get_running_loop().run_in_executor(None, lambda: run(url))

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
    verificar_pagamentos_asaas()

    app = Application.builder().token(TOKEN).build()

    async def set_commands(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Início"),
            BotCommand("planos", "Planos Premium"),
            BotCommand("duvida", "Ajuda"),
            BotCommand("meuid", "Mostrar ID"),
        ])

    app.post_init = set_commands

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/webhook"
    )


if __name__ == "__main__":
    main()
