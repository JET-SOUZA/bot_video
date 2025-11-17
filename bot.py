# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + Instagram Reels + YouTube + yt-dlp
# Atualização 2025-11: addpremium/delpremium + menu admin + mobile fix + contador diário corrigido
# Revisado: cookies IG B64, keepalive Render, fix event loop, /verpremium

import os
import json
import requests
import asyncio
import traceback
import base64
from datetime import datetime, date
from pathlib import Path
from urllib.parse import unquote
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import yt_dlp
import nest_asyncio

# ---------------- CONFIGURAÇÃO ----------------
TOKEN = os.environ.get("TOKEN") or os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Token não encontrado.")

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5593153639"))
LIMITE_DIARIO = int(os.environ.get("LIMITE_DIARIO", "10"))
PORT = int(os.environ.get("PORT", 10000))

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"
COOKIES_INSTAGRAM = SCRIPT_DIR / "cookies_ig.txt"

# ---------------- CARREGAR COOKIES ----------------
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w", encoding="utf-8") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

if "COOKIES_IG_B64" in os.environ:
    try:
        decoded = base64.b64decode(os.environ["COOKIES_IG_B64"]).decode("utf-8")
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(decoded)
        print("Cookies Instagram carregados do COOKIES_IG_B64 com sucesso!")
    except Exception as e:
        print("Erro ao decodificar COOKIES_IG_B64:", e)

# ---------------- UTILIDADES JSON ----------------
def load_json(path: Path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------- SISTEMA PREMIUM ----------------
def load_premium_env():
    db = {}
    raw = os.environ.get("PREMIUM_DB")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                db.update(parsed)
        except Exception as e:
            print("Erro ao parsear PREMIUM_DB:", e)
    file_data = load_json(ARQUIVO_PREMIUM)
    if isinstance(file_data, dict):
        if "premium_users" in file_data:
            for uid in file_data["premium_users"]:
                db[str(uid)] = True
        else:
            for k, v in file_data.items():
                if v:
                    db[str(k)] = True
    return db


def save_premium_env(db: dict):
    try:
        os.environ["PREMIUM_DB"] = json.dumps(db)
    except:
        pass
    save_json(ARQUIVO_PREMIUM, {"premium_users": [int(k) for k in db.keys()]})


_premium_db = load_premium_env()

# Premium fixo
PREMIUM_FIXO = [ADMIN_ID, 908662411]
for uid in PREMIUM_FIXO:
    _premium_db[str(uid)] = True
save_premium_env(_premium_db)


def add_premium(user_id):
    _premium_db[str(int(user_id))] = True
    save_premium_env(_premium_db)


def remove_premium(user_id):
    uid = str(int(user_id))
    if uid in _premium_db:
        del _premium_db[uid]
        save_premium_env(_premium_db)


def is_premium(user_id) -> bool:
    return str(int(user_id)) in _premium_db


def list_premium():
    return sorted(int(k) for k in _premium_db.keys())

# ---------------- ASAAS ----------------
def verificar_pagamentos_asaas():
    if not ASAAS_API_KEY:
        print("Asaas desativado (sem API KEY).")
        return
    try:
        url = f"{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()
        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                uid = int(p["metadata"]["telegram_id"])
                add_premium(uid)
    except Exception as e:
        print("Erro Asaas:", e)

# ---------------- LIMITE DIÁRIO ----------------
def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(uid) not in data:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)
        return 0
    if data[str(uid)]["data"] != hoje:
        data[str(uid)]["data"] = hoje
        data[str(uid)]["downloads"] = 0
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

# ---------------- EXTRATORES ----------------
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
            for regex in [r"https?://[^\s\"']+\.mp4", r"https?://[^\s\"']+\.m3u8[^\s\"']*"]:
                match = re.search(regex, html)
                if match:
                    return match.group(0)
        except:
            pass
    return video_url


def extrair_video_instagram(url, story_id=None):
    try:
        ydl_opts = {"quiet": True, "skip_download": True, "nocheckcertificate": True, "format": "best[ext=mp4]/best"}
        if COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info.get("url"):
            return info.get("url")
        elif info.get("requested_formats"):
            return info["requested_formats"][0].get("url")
        elif info.get("entries"):
            entries = info["entries"]
            if story_id:
                for e in entries:
                    if e.get("id") == str(story_id):
                        return e.get("url")
            return entries[0].get("url")  # default: primeiro story
        else:
            return None
    except Exception as e:
        print("Erro ao extrair vídeo do Instagram:", e)
        return None

# ---------------- HANDLER DE DOWNLOAD ----------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.message.from_user.id
    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    verificar_pagamentos_asaas()
    if not is_premium(uid) and verificar_limite(uid) >= LIMITE_DIARIO:
        return await update.message.reply_text("⚠️ Limite diário atingido.")

    # Shopee
    if any(x in url for x in ["shopee.com", "shp.ee", "sv.shopee.com"]):
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo da Shopee.")
        url = video_url

    # Instagram
    elif any(x in url for x in ["instagram.com", "instagr.am", "ig.me"]):
        await update.message.reply_text("🔄 Processando link do Instagram...")
        story_id_match = re.search(r"/(\d+)/?$", url)
        story_id = story_id_match.group(1) if story_id_match else None
        video_url = extrair_video_instagram(url, story_id=story_id)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo do Instagram.")
        url = video_url

    await update.message.reply_text("⏳ Baixando...")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")
    ydl_opts = {
        "outtmpl": output,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
            {"key": "FFmpegMetadata"},
            {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
        ],
        "postprocessor_args": ["-movflags", "faststart"],
    }
    if COOKIES_TIKTOK.exists():
        ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
    if "instagram" in url and COOKIES_INSTAGRAM.exists():
        ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)

    def run(url_local):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_local, download=True)
            return ydl.prepare_filename(info)

    loop = asyncio.get_running_loop()
    try:
        file_path = await loop.run_in_executor(None, lambda: run(url))
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                await update.message.reply_video(f, caption="✅ Seu vídeo está aqui!")
            try:
                os.remove(file_path)
            except:
                pass
        else:
            await update.message.reply_video(file_path, caption="✅ Seu vídeo está aqui!")
        if not is_premium(uid):
            incrementar_download(uid)
    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# ---------------- CALLBACKS ----------------
async def callbacks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = (query.data or "").lower()
    if data == "planos":
        await planos(update, context)
    elif data == "duvida":
        await duvida(update, context)
    elif data == "addpremium":
        await addpremium(update, context)
    elif data == "delpremium":
        await delpremium(update, context)
    else:
        await query.answer()

# ---------------- KEEPALIVE ----------------
async def keepalive_task():
    await asyncio.sleep(5)
    while True:
        try:
            host = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("RENDER_EXTERNAL_URL")
            if host:
                requests.get(f"https://{host}/webhook", timeout=5)
        except:
            pass
        await asyncio.sleep(300)

# ---------------- COMANDOS ----------------
# ... start, planos, duvida, meuid, addpremium, delpremium, verpremium (mesmo do seu bot) ...

# ---------------- MAIN ----------------
async def main():
    verificar_pagamentos_asaas()
    app = Application.builder().token(TOKEN).build()

    await app.bot.set_my_commands([
        BotCommand("start", "Iniciar bot"),
        BotCommand("planos", "Planos premium"),
        BotCommand("duvida", "Ajuda"),
        BotCommand("meuid", "Mostrar ID"),
        BotCommand("addpremium", "Adicionar premium (admin)"),
        BotCommand("delpremium", "Remover premium (admin)"),
        BotCommand("verpremium", "Visualizar premium (admin)"),
    ])

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(CommandHandler("verpremium", verpremium))
    app.add_handler(CallbackQueryHandler(callbacks_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    asyncio.create_task(keepalive_task())

    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("RENDER_EXTERNAL_URL")
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{host}/webhook" if host else None,
    )

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
