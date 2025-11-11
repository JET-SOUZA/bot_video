# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + yt-dlp

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


# ---------------------------------------------------------
# TOKEN (Render)
# ---------------------------------------------------------
TOKEN = (
    os.environ.get("TOKEN") or
    os.environ.get("BOT_TOKEN") or
    os.environ.get("TELEGRAM_TOKEN") or
    os.environ.get("TG_BOT_TOKEN")
)

if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN no Render.")


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

if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])


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
            print("Asaas desativado. Sem API KEY.")
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
    await update.message.reply_text(
        "🎬 *Jet TikTokShop Bot*\n\n"
        "Envie um link para baixar vídeo.\n"
        "⚠️ Free: 10/dia\n"
        "💎 Premium: ilimitado",
        parse_mode="Markdown"
    )

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
# SHOPEE UNIVERSAL PATCH 2025 (FINAL)
# ---------------------------------------------------------
def extrair_video_shopee(url):
    """
    PATCH UNIVERSAL 2025 — SUPORTA TODOS OS FORMATOS:
    - br.shp.ee / shp.ee
    - universal-link?redir=
    - share-video/ID
    - item/get (com vídeo interno)
    - vídeos carregados via XHR no HTML
    """
    import requests, re
    from urllib.parse import unquote

    # 1) Se contém redir=
    if "redir=" in url:
        try:
            redir = re.search(r"redir=([^&]+)", url).group(1)
            url = unquote(redir)
        except:
            pass

    # 2) Seguir redirecionamentos (GET — obrigatório para br.shp.ee)
    try:
        r = requests.get(url, allow_redirects=True, timeout=12)
        final = r.url
        html_fallback = r.text
        url = final
    except:
        html_fallback = ""

    # 3) share-video ID
    m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", url) or \
        re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html_fallback)

    if m:
        share_id = m.group(1)
        api_url = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"

        try:
            data = requests.get(api_url, timeout=10).json()
        except:
            data = {}

        # múltiplos padrões possíveis
        video_url = (
            data.get("data", {}).get("play") or
            data.get("data", {}).get("url") or
            data.get("data", {}).get("video_url") or
            data.get("data", {}).get("path") or
            (data.get("data", {}).get("videos", [{}])[0].get("url")
             if data.get("data", {}).get("videos") else None)
        )

        if video_url:
            return video_url

    # 4) Página /item (produto com vídeo interno)
    try:
        if "/item/" in url or "/item/get" in url:
            txt = requests.get(url, timeout=12).text

            mp4 = re.search(r"https://[^\"']+\.mp4", txt)
            if mp4:
                return mp4.group(0)

            m3u8 = re.search(r"https://[^\"']+\.m3u8[^\"']*", txt)
            if m3u8:
                return m3u8.group(0)

            js = re.search(r'"(play|url|play_url)"\s*:\s*"([^"]+)"', txt)
            if js:
                return js.group(2)
    except:
        pass

    # 5) Fallback absoluto
    txt = html_fallback

    mp4 = re.search(r"https://[^\"']+\.mp4", txt)
    if mp4:
        return mp4.group(0)

    m3u8 = re.search(r"https://[^\"']+\.m3u8[^\"']*", txt)
    if m3u8:
        return m3u8.group(0)

    ju = re.search(r'"url":"(https:[^"]+)"', txt)
    if ju:
        return ju.group(1)

    jp = re.search(r'"play[^"]*":"(https:[^"]+)"', txt)
    if jp:
        return jp.group(1)

    return None


# ---------------------------------------------------------
# DOWNLOAD HANDLER
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

    # Patch Shopee
    if "shopee.com" in url or "shp.ee" in url or "sv.shopee.com" in url:
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)

        if not video_url:
            return await update.message.reply_text("❌ Não foi possível obter o vídeo da Shopee.")

        url = video_url  # agora o yt-dlp baixa direto

    # ----------- yt-dlp ----------------------------------
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
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")


# ---------------------------------------------------------
# MAIN (WEBHOOK)
# ---------------------------------------------------------
def main():
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
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
