# BOT COMPLETO COM PATCH SHOPEE 2025

import os
import json
import requests
import asyncio
import traceback
from datetime import datetime, date
from pathlib import Path
from urllib.parse import unquote
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

import yt_dlp

TOKEN = os.environ.get("TOKEN") or os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TG_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN no Render.")

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"
ADMIN_ID = 5593153639
LIMITE_DIARIO = 10
PORT = int(os.environ.get("PORT", 10000))

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

# JSON utils
def load_json(path):
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

USUARIOS_PREMIUM = set(map(int, load_json(ARQUIVO_PREMIUM).get("premium_users", [])))
USUARIOS_PREMIUM.add(ADMIN_ID)
save_json(ARQUIVO_PREMIUM, {"premium_users": list(USUARIOS_PREMIUM)})

# Shopee patch
def extrair_video_shopee(url):
    headers = {"User-Agent": "Mozilla/5.0"}

    def find_media(text):
        if not text:
            return None
        # corrigido escape correto da regex
        mp4 = re.search(r'https?://[^"\']+\.mp4', text)
        if mp4:
            return mp4.group(0)
        m3u8 = re.search(r'https?://[^"\']+\.m3u8[^"\']*', text)
        if m3u8:
            return m3u8.group(0)
        return None

    try:
        r = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        html = r.text
    except:
        return None

    direct = find_media(html)
    if direct:
        return direct

    return None

# Telegram handler
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.message.from_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    if "shopee" in url or "shp.ee" in url:
        await update.message.reply_text("🔍 Analisando Shopee...")
        real = extrair_video_shopee(url)
        if not real:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo.")
        url = real

    await update.message.reply_text("⏳ Baixando...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")
        ydl_opts = {"outtmpl": output, "format": "best"}

        def run(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        fp = await loop.run_in_executor(None, lambda: run(url))

        with open(fp, "rb") as f:
            await update.message.reply_video(f)

        os.remove(fp)

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro: {e}")

# Main
from telegram.ext import Application

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))
    app.run_webhook(listen="0.0.0.0", port=PORT, url_path="webhook", webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/webhook")

if __name__ == "__main__":
    main()
