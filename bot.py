# Jet TikTokShop Bot - Render + PTB20 Webhook Nativo + Shopee Support

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import yt_dlp
import os
import json
import asyncio
import traceback
from datetime import date, datetime
from pathlib import Path
import urllib.parse
import aiohttp
import re

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

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
# JSON
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
USUARIOS_PREMIUM.update({ADMIN_ID})
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
# SHOPEE NORMALIZER + API EXTRACTOR
# -------------------------
def resolver_shopee(url: str) -> str:
    if "shopee.com" in url and "universal-link" in url:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        if "redir" in params:
            return urllib.parse.unquote(params["redir"][0])
    return url

async def get_shopee_video(url: str) -> str | None:
    match = re.search(r"/share-video/([^?]+)", url)
    if not match:
        return None

    vid = match.group(1)
    api = f"https://sv.shopee.com.br/api/v4/mms/meta?video_id={vid}"

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(api, timeout=10) as resp:
                data = await resp.json()

        fmts = data.get("data", {}).get("video_info", {}).get("formats", [])
        if not fmts:
            return None

        return fmts[0].get("url")
    except:
        return None

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
    url = resolver_shopee(update.message.text.strip())
    uid = update.message.from_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    if uid not in USUARIOS_PREMIUM:
        if verificar_limite(uid) >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    # -------------------------
    # SHOPEE
    # -------------------------
    if "sv.shopee.com.br/share-video" in url:
        await update.message.reply_text("⏳ Obtendo vídeo da Shopee...")

        mp4 = await get_shopee_video(url)
        if not mp4:
            return await update.message.reply_text("❌ Não foi possível obter o vídeo da Shopee.")

        try:
            file_path = DOWNLOADS_DIR / f"shopee_{datetime.now().timestamp()}.mp4"

            async with aiohttp.ClientSession() as s:
                async with s.get(mp4) as resp:
                    with open(file_path, "wb") as f:
                        f.write(await resp.read())

            with open(file_path, "rb") as f:
                await update.message.reply_video(f, caption="✅ Vídeo da Shopee!")

            os.remove(file_path)

            if uid not in USUARIOS_PREMIUM:
                uso = incrementar_download(uid)
                await update.message.reply_text(f"📊 Uso: {uso}/{LIMITE_DIARIO}")

        except Exception as e:
            print("Shopee Error:", e)
            return await update.message.reply_text("❌ Falha ao baixar vídeo da Shopee.")

        return

    # -------------------------
    # YT-DLP
    # -------------------------
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
