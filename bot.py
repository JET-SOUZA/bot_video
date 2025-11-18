import os
import time
import json
import base64
import secrets
import asyncio
import traceback
import requests
import yt_dlp
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler
)

# ---------------------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------------------
TOKEN = os.environ.get("TOKEN") or os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TG_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN ou BOT_TOKEN no Render.")

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5593153639"))
LIMITE_DIARIO = int(os.environ.get("LIMITE_DIARIO", "10"))
PORT = int(os.environ.get("PORT", 10000))

SCRIPT_DIR = Path(__file__).parent
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
ARQUIVO_CONTADOR_YT = SCRIPT_DIR / "downloads_youtube.json"
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"

COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"
COOKIES_INSTAGRAM = SCRIPT_DIR / "cookies_ig.txt"
COOKIES_YOUTUBE = SCRIPT_DIR / "cookies_yt.txt"

YT_FREE_LIMIT = 3
YT_PENDING = {}  # token -> {"url":..., "uid":..., "ts":...}

PREMIUM_FIXO = {str(ADMIN_ID), "908662411"}

# ---------------------------------------------------------
# FUNÇÕES AUXILIARES
# ---------------------------------------------------------

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

# ---------------------------------------------------------
# PREMIUM
# ---------------------------------------------------------
def load_premium_env():
    db = {}
    raw = os.environ.get("PREMIUM_DB")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                db.update(parsed)
        except:
            pass
    try:
        file_data = load_json(ARQUIVO_PREMIUM)
        if isinstance(file_data, dict):
            if "premium_users" in file_data and isinstance(file_data["premium_users"], list):
                for uid in file_data["premium_users"]:
                    db[str(uid)] = True
            else:
                for k in file_data.keys():
                    db[str(k)] = True
    except:
        pass
    for uid in PREMIUM_FIXO:
        db[uid] = True
    save_json(ARQUIVO_PREMIUM, {"premium_users": [int(k) for k in db.keys()]})
    return db

def save_premium_env(db: dict):
    try:
        os.environ["PREMIUM_DB"] = json.dumps(db)
    except:
        pass
    ulist = [int(k) for k in db.keys()]
    save_json(ARQUIVO_PREMIUM, {"premium_users": ulist})

_premium_db = load_premium_env()

def add_premium(user_id):
    uid = str(user_id)
    _premium_db[uid] = True
    save_premium_env(_premium_db)

def remove_premium(user_id):
    uid = str(user_id)
    if uid in _premium_db and uid not in PREMIUM_FIXO:
        del _premium_db[uid]
        save_premium_env(_premium_db)

def is_premium(user_id) -> bool:
    return str(user_id) in _premium_db

def list_premium():
    return sorted(int(k) for k in _premium_db.keys())

def get_premium_status():
    fixos = set(PREMIUM_FIXO)
    dinamicos = set(int(k) for k in _premium_db.keys() if k not in fixos)
    return fixos, dinamicos

# ---------------------------------------------------------
# LIMITES DIÁRIOS
# ---------------------------------------------------------
def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)
        return 0
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

def verificar_limite_youtube(uid):
    data = load_json(ARQUIVO_CONTADOR_YT)
    hoje = str(date.today())
    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR_YT, data)
        return 0
    return data[str(uid)]["downloads"]

def incrementar_download_youtube(uid):
    data = load_json(ARQUIVO_CONTADOR_YT)
    hoje = str(date.today())
    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        data[str(uid)]["downloads"] += 1
    save_json(ARQUIVO_CONTADOR_YT, data)
    return data[str(uid)]["downloads"]

# ---------------------------------------------------------
# ASAAS PREMIUM AUTOMÁTICO
# ---------------------------------------------------------
def verificar_pagamentos_asaas():
    if not ASAAS_API_KEY: return
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

# ---------------------------------------------------------
# COOKIES
# ---------------------------------------------------------
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w", encoding="utf-8") as f:
        f.write(os.environ["COOKIES_TIKTOK"])
    print("Cookies TikTok carregados do env COOKIES_TIKTOK.")

if "COOKIES_IG_B64" in os.environ and not COOKIES_INSTAGRAM.exists():
    try:
        decoded = base64.b64decode(os.environ["COOKIES_IG_B64"]).decode("utf-8")
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(decoded)
        print("Cookies Instagram carregados do COOKIES_IG_B64 com sucesso!")
    except Exception as e:
        print("Erro ao decodificar COOKIES_IG_B64:", e)

def load_youtube_cookies_from_env():
    b64 = os.environ.get("COOKIES_YT_B64")
    if not b64:
        return None
    decoded = base64.b64decode(b64).decode("utf-8")
    with open(COOKIES_YOUTUBE, "w", encoding="utf-8") as f:
        f.write(decoded)
    print("Cookies YouTube carregados a partir de COOKIES_YT_B64.")
    return str(COOKIES_YOUTUBE)

# ---------------------------------------------------------
# EXTRAÇÃO DE VÍDEOS
# ---------------------------------------------------------
def extrair_video_shopee(url):
    try:
        if "br.shp.ee" in url or "shp.ee" in url:
            r = requests.head(url, allow_redirects=True, timeout=10)
            url = r.url
        if "redir=" in url:
            redir = re.search(r"redir=([^&]+)", url).group(1)
            url = unquote(redir)
        m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", url)
        if not m:
            html = requests.get(url, timeout=10).text
            m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html)
        if not m:
            return None
        share_id = m.group(1)
        api_url = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
        data = requests.get(api_url, timeout=10).json()
        video_url = (
            data.get("data", {}).get("play")
            or data.get("data", {}).get("video_url")
            or data.get("data", {}).get("url")
            or (data.get("data", {}).get("videos", [{}])[0].get("url") if data.get("data", {}).get("videos") else None)
            or data.get("data", {}).get("path")
        )
        return video_url
    except:
        return None

def extrair_video_instagram(url):
    try:
        clean_url = url.split("?")[0]
        ydl_opts = {"quiet": True, "skip_download": True, "nocheckcertificate": True, "format": "best[ext=mp4]/best"}
        if COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
        if info.get("url"):
            return info.get("url")
        elif info.get("requested_formats"):
            return info["requested_formats"][0].get("url")
        elif info.get("entries"):
            return info["entries"][0].get("url")
        else:
            return None
    except Exception as e:
        print("Erro ao extrair vídeo do Instagram:", e)
        return None

# ---------------------------------------------------------
# FUNÇÕES YOUTUBE
# ---------------------------------------------------------
def _make_yt_token():
    return secrets.token_hex(8)

def _cleanup_pending():
    now = time.time()
    to_del = [k for k,v in list(YT_PENDING.items()) if now - v.get("ts",0) > 20*60]
    for k in to_del:
        del YT_PENDING[k]

def _build_yt_keyboard(token: str, is_premium_user: bool, used: int):
    row1 = [
        InlineKeyboardButton("360p", callback_data=f"yt_start:{token}:360"),
        InlineKeyboardButton("480p", callback_data=f"yt_start:{token}:480"),
        InlineKeyboardButton("MP3", callback_data=f"yt_start:{token}:mp3"),
    ]
    if is_premium_user:
        row2 = [
            InlineKeyboardButton("720p", callback_data=f"yt_start:{token}:720"),
            InlineKeyboardButton("1080p", callback_data=f"yt_start:{token}:1080"),
            InlineKeyboardButton("2K", callback_data=f"yt_start:{token}:1440"),
        ]
        row3 = [InlineKeyboardButton("4K", callback_data=f"yt_start:{token}:2160")]
    else:
        row2 = [
            InlineKeyboardButton("720p 🔒", callback_data=f"yt_locked"),
            InlineKeyboardButton("1080p 🔒", callback_data=f"yt_locked"),
            InlineKeyboardButton("2K 🔒", callback_data=f"yt_locked"),
        ]
        row3 = [InlineKeyboardButton("4K 🔒", callback_data=f"yt_locked")]
    status = InlineKeyboardButton(
        f"🔢 YouTube: {used}/{YT_FREE_LIMIT} usados hoje" if not is_premium_user else "🔓 Premium: downloads ilimitados",
        callback_data="yt_info"
    )
    kb = [row1, row2, row3, [status]]
    return InlineKeyboardMarkup(kb)

# ---------------------------------------------------------
# HANDLERS DE COMANDOS
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texto = (
        "Bem-vindo!\n\n"
        "⚠️ Free: 10/dia\n"
        "💎 Premium: ilimitado"
    )
    botoes = [
        [InlineKeyboardButton("💎 Planos", callback_data="planos")],
        [InlineKeyboardButton("🆘 Suporte", callback_data="duvida")]
    ]
    if user_id == ADMIN_ID:
        botoes.append([InlineKeyboardButton("➕ Add Premium", callback_data="addpremium")])
        botoes.append([InlineKeyboardButton("❌ Del Premium", callback_data="delpremium")])
    kb = InlineKeyboardMarkup(botoes)
    await update.message.reply_text(texto, reply_markup=kb)

# Comandos admin
async def addpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Use /addpremium <user_id>")
    uid = int(context.args[0])
    add_premium(uid)
    await update.message.reply_text(f"✅ Usuário {uid} adicionado ao Premium!")

async def delpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Use /delpremium <user_id>")
    uid = int(context.args[0])
    remove_premium(uid)
    await update.message.reply_text(f"❌ Usuário {uid} removido do Premium.")

async def verpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    fixos, dinamicos = get_premium_status()
    texto = "💎 *Usuários Premium:*\n\n"
    texto += "📌 *Fixos (permanentes):*\n" + ("\n".join(str(uid) for uid in sorted(fixos)) or "Nenhum") + "\n\n"
    texto += "⚡ *Dinâmicos (temporários/Asaas):*\n" + ("\n".join(str(uid) for uid in sorted(dinamicos)) or "Nenhum")
    await update.message.reply_text(texto, parse_mode="Markdown")

# ---------------------------------------------------------
# CALLBACK HANDLER
# ---------------------------------------------------------
async def callbacks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # YouTube locked
    if data == "yt_locked":
        return await query.answer("⚠️ Esta qualidade está disponível apenas para usuários Premium.", show_alert=True)
    if data == "yt_info":
        return await query.answer("Escolha a qualidade para iniciar o download.", show_alert=False)
    if data.startswith("yt_start:"):
        parts = data.split(":")
        if len(parts) != 3:
            return await query.answer("Erro interno (callback inválido).", show_alert=True)
        token = parts[1]
        quality = parts[2]
        pending = YT_PENDING.get(token)
        if not pending:
            return await query.answer("Sessão expirada. Envie o link novamente.", show_alert=True)
        uid = pending["uid"]
        url = pending["url"]
        if query.from_user.id != uid:
            return await query.answer("Esses botões não são para você.", show_alert=True)
        if not is_premium(uid) and verificar_limite_youtube(uid) >= YT_FREE_LIMIT:
            return await query.answer("⚠️ Limite diário do YouTube atingido (3 downloads).", show_alert=True)
        await query.edit_message_text("⏳ Iniciando download...")
        # Aqui você integra download com download_youtube_file (igual código original)
        # ...
        # Após envio, incremente contador:
        if not is_premium(uid):
            incrementar_download_youtube(uid)
        try: del YT_PENDING[token]
        except: pass
        return

# ---------------------------------------------------------
# KEEPALIVE
# ---------------------------------------------------------
async def keepalive_task():
    while True:
        try:
            requests.get("https://google.com", timeout=5)
        except: pass
        await asyncio.sleep(300)

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
async def main():
    verificar_pagamentos_asaas()
    load_youtube_cookies_from_env()

    app = Application.builder().token(TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(CommandHandler("verpremium", verpremium))
    app.add_handler(CommandHandler("download", download_command))

    # CallbackQuery
    app.add_handler(CallbackQueryHandler(callbacks_handler))

    # Keepalive
    asyncio.create_task(keepalive_task())

    print("Bot iniciado com sucesso!")

    # PEGAR HOST DO RENDER
    host = (
        os.environ.get("RENDER_EXTERNAL_HOSTNAME")
        or os.environ.get("RENDER_EXTERNAL_URL")
    )

    # INICIAR WEBHOOK
    await app.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{host}/webhook" if host else None,
    )

    # Mantém o bot rodando
    await app.idle()
if __name__ == "__main__":
    asyncio.run(main())



