# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee + Instagram + YouTube + yt-dlp
# Atualização 2025-11: suporte cookies YouTube + safe fallback

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
import nest_asyncio

# ---------------------------------------------------------
# TOKEN (Render)
# ---------------------------------------------------------
TOKEN = (
    os.environ.get("TOKEN")
    or os.environ.get("BOT_TOKEN")
    or os.environ.get("TELEGRAM_TOKEN")
    or os.environ.get("TG_BOT_TOKEN")
)
if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN ou BOT_TOKEN no Render.")

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
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
COOKIES_INSTAGRAM = SCRIPT_DIR / "cookies_ig.txt"
COOKIES_YOUTUBE = SCRIPT_DIR / "cookies_yt.txt"

# ---------------------------------------------------------
# COOKIES HANDLER
# ---------------------------------------------------------
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

if "COOKIES_INSTAGRAM" in os.environ and not COOKIES_INSTAGRAM.exists():
    with open(COOKIES_INSTAGRAM, "w") as f:
        f.write(os.environ["COOKIES_INSTAGRAM"])

if "COOKIES_YOUTUBE" in os.environ and not COOKIES_YOUTUBE.exists():
    with open(COOKIES_YOUTUBE, "w") as f:
        f.write(os.environ["COOKIES_YOUTUBE"])

# ---------------------------------------------------------
# JSON UTILS
# ---------------------------------------------------------
def load_json(path):
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

# ---------------------------------------------------------
# PREMIUM
# ---------------------------------------------------------
def load_premium():
    data = load_json(ARQUIVO_PREMIUM)
    return set(map(int, data.get("premium_users", [])))

def save_premium(users):
    save_json(ARQUIVO_PREMIUM, {"premium_users": list(users)})

USUARIOS_PREMIUM = load_premium()
USUARIOS_PREMIUM.add(ADMIN_ID)
save_premium(USUARIOS_PREMIUM)

# ---------------------------------------------------------
# ASAAS — PREMIUM AUTOMÁTICO
# ---------------------------------------------------------
def verificar_pagamentos_asaas():
    try:
        if not ASAAS_API_KEY:
            print("Asaas desativado (sem API KEY).")
            return
        url = f"{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()
        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                uid = int(p["metadata"]["telegram_id"])
                USUARIOS_PREMIUM.add(uid)
        save_premium(USUARIOS_PREMIUM)
    except Exception as e:
        print("Erro Asaas:", e)

# ---------------------------------------------------------
# LIMITE DIÁRIO
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# COMANDOS
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texto = (
        "🎬 *Jet TikTokShop Bot*\n\n"
        "Envie um link para baixar vídeo.\n"
        "⚠️ Free: 10/dia\n"
        "💎 Premium: ilimitado"
    )
    botoes = [
        [InlineKeyboardButton("💎 Planos", callback_data="planos")],
        [InlineKeyboardButton("🆘 Suporte", callback_data="duvida")],
    ]
    if user_id == ADMIN_ID:
        botoes += [
            [InlineKeyboardButton("➕ Add Premium", callback_data="addpremium")],
            [InlineKeyboardButton("➖ Remover Premium", callback_data="delpremium")],
        ]
    await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💎 1 Mês – R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses – R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano – R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")],
    ]
    await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")

# ---------------------------------------------------------
# ADMIN COMANDOS
# ---------------------------------------------------------
async def addpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /addpremium <user_id>")
    uid = int(context.args[0])
    USUARIOS_PREMIUM.add(uid)
    save_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"✅ Usuário {uid} adicionado ao Premium!")

async def delpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /delpremium <user_id>")
    uid = int(context.args[0])
    if uid in USUARIOS_PREMIUM:
        USUARIOS_PREMIUM.remove(uid)
        save_premium(USUARIOS_PREMIUM)
        await update.message.reply_text(f"❌ Usuário {uid} removido do Premium.")
    else:
        await update.message.reply_text("Usuário não está no Premium.")

# ---------------------------------------------------------
# SHOPEE PATCH
# ---------------------------------------------------------
def extrair_video_shopee(url):
    if "br.shp.ee" in url or "shp.ee" in url:
        try:
            r = requests.head(url, allow_redirects=True, timeout=10)
            url = r.url
        except:
            pass
    if "redir=" in url:
        try:
            redir = re.search(r"redir=([^&]+)", url).group(1)
            url = unquote(redir)
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
        return None

    share_id = m.group(1)
    api_url = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
    try:
        data = requests.get(api_url, timeout=10).json()
    except:
        data = {}

    video_url = (
        data.get("data", {}).get("play")
        or data.get("data", {}).get("video_url")
        or data.get("data", {}).get("url")
        or (data.get("data", {}).get("videos", [{}])[0].get("url") if data.get("data", {}).get("videos") else None)
        or data.get("data", {}).get("path")
    )
    if not video_url:
        try:
            html = requests.get(url, timeout=10).text
            for regex in [
                r"https?://[^\s\"']+\.mp4",
                r"https?://[^\s\"']+\.m3u8[^\s\"']*",
                r'"url":"(https:[^"]+)"',
                r'"play[^"]*":"(https:[^"]+)"',
            ]:
                match = re.search(regex, html)
                if match:
                    return match.group(1) if len(match.groups()) else match.group(0)
        except:
            pass
    return video_url

# ---------------------------------------------------------
# INSTAGRAM PATCH
# ---------------------------------------------------------
def extrair_video_instagram(url):
    try:
        clean_url = url.split("?")[0]
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "format": "best[ext=mp4]/best",
        }
        if COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            return info.get("url") or info.get("requested_formats", [{}])[0].get("url")
    except Exception as e:
        print("Erro ao extrair vídeo do Instagram:", e)
        return None

# ---------------------------------------------------------
# DOWNLOAD HANDLER (com suporte YouTube)
# ---------------------------------------------------------
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

    # Shopee
    if "shopee.com" in url or "shp.ee" in url or "sv.shopee.com" in url:
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo da Shopee.")
        url = video_url

    # Instagram
    elif any(x in url for x in ["instagram.com", "instagr.am", "ig.me"]):
        await update.message.reply_text("🔄 Processando link do Instagram...")
        video_url = extrair_video_instagram(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo do Instagram (pode ser privado).")
        url = video_url

    await update.message.reply_text("⏳ Baixando...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        ydl_opts = {
            "outtmpl": output,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
                {"key": "FFmpegMetadata"},
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
            ],
            "postprocessor_args": ["-movflags", "faststart"],
        }

        # cookies dinâmicos
        if "youtube.com" in url or "youtu.be" in url:
            if COOKIES_YOUTUBE.exists():
                ydl_opts["cookiefile"] = str(COOKIES_YOUTUBE)
        elif "instagram" in url and COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        elif COOKIES_TIKTOK.exists():
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
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# ---------------------------------------------------------
# MAIN (WEBHOOK)
# ---------------------------------------------------------
async def main():
    verificar_pagamentos_asaas()
    app = Application.builder().token(TOKEN).build()

    async def set_commands(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Iniciar bot"),
            BotCommand("planos", "Planos premium"),
            BotCommand("duvida", "Ajuda"),
            BotCommand("meuid", "Mostrar ID"),
            BotCommand("addpremium", "Adicionar premium (admin)"),
            BotCommand("delpremium", "Remover premium (admin)"),
        ])
    app.post_init = set_commands

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    print(f"Iniciando bot (webhook) na porta {PORT}...")
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/webhook",
    )

# ---------------------------------------------------------
# EXECUÇÃO SEGURA PARA RENDER
# ---------------------------------------------------------
if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
