# Jet TikTokShop Bot - Arquitetura C + Shopee Patch Absoluto + Safe Input + LOGS
# PTB20 Webhook + Asaas + TikTok

import os
import json
import requests
import traceback
import asyncio
from datetime import datetime, date
from pathlib import Path
from urllib.parse import unquote
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

import yt_dlp

# -------------------------
# CONFIGURAÇÃO
# -------------------------
TOKEN = os.environ.get("TOKEN") or "8249697837:AAGfvejL5PT9w8sSPMZnIwErh0jX-XMpAPE"
if not TOKEN:
    raise ValueError("❌ Variável de ambiente TOKEN não definida!")

ADMIN_ID = 5593153639
LIMITE_DIARIO = 10
PORT = int(os.environ.get("PORT", 10000))
ASAAS_BASE_URL = os.environ.get("ASAAS_BASE_URL", "")
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY", "")

SCRIPT_DIR = Path(__file__).parent
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

# -------------------------
# UTILS JSON
# -------------------------

def load_json(path):
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

# -------------------------
# PREMIUM
# -------------------------
USUARIOS_PREMIUM = set()
USUARIOS_PREMIUM.add(ADMIN_ID)


def save_premium(users):
    save_json(SCRIPT_DIR / "premium.json", list(users))

# -------------------------
# CHECK ASAAS
# -------------------------

def if ASAAS_BASE_URL and ASAAS_API_KEY:
        verificar_pagamentos_asaas()
    else:
        print("Asaas desativado (faltam variáveis ASAAS)."):
    try:
        url = f"{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()
        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                uid = int(p["metadata"]["telegram_id"])
                USUARIOS_PREMIUM.add(uid)
        save_premium(USUARIOS_PREMIUM)
    except Exception as e:
        print("ERRO ASAAS:", e)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Jet TikTokShop Bot*\n\n"
        "Envie um link de vídeo para baixar.\n"
        "⚠️ Free: 10 downloads/dia\n"
        "💎 Premium: ilimitado",
        parse_mode="Markdown"
    )


async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💎 1 Mês – R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses – R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano – R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")]
    ]
    await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))


async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")


async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")

# -------------------------
# DOWNLOAD + SHOPEE PATCH + LOGS
# -------------------------

async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.message.from_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    verificar_pagamentos_asaas()

    if uid not in USUARIOS_PREMIUM:
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    # ✅ PATCH SHOPEE UNIVERSAL COMPLETO
    if "shopee.com" in url or "sv.shopee.com" in url:
        await update.message.reply_text("🔄 Resolvendo link da Shopee...")
        try:
            if "universal-link" in url and "redir=" in url:
                try:
                    redir = re.search(r"redir=([^&]+)", url).group(1)
                    url = unquote(redir)
                except:
                    pass

            try:
                r = requests.head(url, allow_redirects=True, timeout=10)
                url = r.url
            except:
                pass

            m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", url)
            if not m:
                try:
                    html = requests.get(url, timeout=10).text
                    m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html)
                except:
                    pass

            if not m:
                return await update.message.reply_text("❌ Não consegui extrair o ID da Shopee.")

            share_id = m.group(1)
            api_url = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
            data = requests.get(api_url, timeout=10).json()

            if "data" not in data or "play" not in data["data"]:
                return await update.message.reply_text("❌ Shopee não retornou o link direto.")

            url = data["data"]["play"]

        except Exception as e:
            return await update.message.reply_text(f"❌ Erro Shopee: {e}")

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
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# -------------------------
# MAIN (WEBHOOK)
# -------------------------

def main():
    verificar_pagamentos_asaas()
    app = Application.builder().token(TOKEN).build()

    async def set_cmds(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Início"),
            BotCommand("planos", "Planos Premium"),
            BotCommand("duvida", "Ajuda"),
            BotCommand("meuid", "Meu ID"),
        ])

    app.post_init = set_cmds

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/webhook"
    )


if __name__ == "__main__":
    main()
