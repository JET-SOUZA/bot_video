# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + Instagram Reels + YouTube + yt-dlp
# Atualização 2025-11: addpremium/delpremium + menu admin + mobile fix + contador diário corrigido + premium fixo/dinâmico
# Revisado: cookies IG B64, keepalive Render, fix event loop, /verpremium detalhado

import os
import json
import requests
import asyncio
import traceback
import base64
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote
import re
import secrets
import time

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

# YT: import module
from youtube_downloader import download_youtube_file

# ---------------------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------------------
TOKEN = os.environ.get("TOKEN") or os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN ou BOT_TOKEN no Render.")

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5593153639"))
LIMITE_DIARIO = int(os.environ.get("LIMITE_DIARIO", "10"))
PORT = int(os.environ.get("PORT", 10000))

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
ARQUIVO_CONTADOR_YT = SCRIPT_DIR / "downloads_youtube.json"
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"

COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"
COOKIES_INSTAGRAM = SCRIPT_DIR / "cookies_ig.txt"
COOKIES_YOUTUBE = SCRIPT_DIR / "cookies_yt.txt"

YT_FREE_LIMIT = 3  # free users: 3 downloads per day
YT_PENDING = {}    # token -> {"url":..., "uid":..., "ts":...}

PREMIUM_FIXO = {str(ADMIN_ID), "908662411"}

# ---------------------------------------------------------
# CARREGAR COOKIES
# ---------------------------------------------------------
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w", encoding="utf-8") as f:
        f.write(os.environ["COOKIES_TIKTOK"])
    print("Cookies TikTok carregados do env COOKIES_TIKTOK.")

if "COOKIES_IG_B64" in os.environ:
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
    try:
        data = base64.b64decode(b64)
        with open(COOKIES_YOUTUBE, "wb") as f:
            f.write(data)
        print("Cookies YouTube carregados a partir de COOKIES_YT_B64.")
        return str(COOKIES_YOUTUBE)
    except Exception as e:
        print("Erro ao decodificar/gravar COOKIES_YT_B64:", e)
        return None

# ---------------------------------------------------------
# FUNÇÕES JSON
# ---------------------------------------------------------
def load_json(path: Path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------
# SISTEMA PREMIUM
# ---------------------------------------------------------
def load_premium_env():
    db = {}
    raw = os.environ.get("PREMIUM_DB")
    if raw:
        try: db.update(json.loads(raw))
        except: pass
    try:
        file_data = load_json(ARQUIVO_PREMIUM)
        if isinstance(file_data, dict):
            if "premium_users" in file_data:
                for uid in file_data["premium_users"]:
                    db[str(uid)] = True
            else:
                for k in file_data.keys():
                    db[str(k)] = True
    except: pass
    for uid in PREMIUM_FIXO:
        db[uid] = True
    save_json(ARQUIVO_PREMIUM, {"premium_users": [int(k) for k in db.keys()]})
    return db

_premium_db = load_premium_env()

def add_premium(user_id):
    _premium_db[str(user_id)] = True
    save_json(ARQUIVO_PREMIUM, {"premium_users": [int(k) for k in _premium_db.keys()]})

def remove_premium(user_id):
    uid = str(user_id)
    if uid in _premium_db and uid not in PREMIUM_FIXO:
        del _premium_db[uid]
        save_json(ARQUIVO_PREMIUM, {"premium_users": [int(k) for k in _premium_db.keys()]})

def is_premium(user_id):
    return str(user_id) in _premium_db

def get_premium_status():
    fixos = set(PREMIUM_FIXO)
    dinamicos = set(_premium_db.keys()) - fixos
    return fixos, dinamicos

# ---------------------------------------------------------
# ASAAS PREMIUM AUTOMÁTICO
# ---------------------------------------------------------
def verificar_pagamentos_asaas():
    if not ASAAS_API_KEY: return
    try:
        url = f"https://www.asaas.com/api/v3/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()
        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                add_premium(int(p["metadata"]["telegram_id"]))
    except Exception as e:
        print("Erro Asaas:", e)

# ---------------------------------------------------------
# CONTADOR DIÁRIO
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

def verificar_limite_youtube(uid):
    data = load_json(ARQUIVO_CONTADOR_YT)
    hoje = str(date.today())
    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR_YT, data)
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
# COMANDOS BÁSICOS
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texto = (
        "🎬 *Jet TikTokShop Bot*\n\n"
        "Envie um link para baixar vídeo.\n"
        "⚠️ Free: 10/dia\n"
        "💎 Premium: ilimitado"
    )
    botoes = [[InlineKeyboardButton("💎 Planos", callback_data="planos")],
              [InlineKeyboardButton("🆘 Suporte", callback_data="duvida")]]
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
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("📞 Suporte: lavimurtha@gmail.com")
    else:
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
    add_premium(uid)
    await update.message.reply_text(f"✅ Usuário {uid} adicionado ao Premium!")

async def delpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /delpremium <user_id>")
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
# CALLBACKS, YT FLOW, BAIXAR VIDEO, ETC
# ---------------------------------------------------------
# Aqui você mantém todas as funções de extrair Shopee, Instagram,
# baixar vídeos, callbacks do YT etc. iguais ao seu código original
# (mantendo async, run_in_executor, _cleanup_pending, _build_yt_keyboard etc.)
# Para economizar espaço, essa parte permanece idêntica

# ---------------------------------------------------------
# KEEPALIVE RENDER
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# MAIN CORRETO PARA RENDER
# ---------------------------------------------------------
async def main():
    verificar_pagamentos_asaas()
    load_youtube_cookies_from_env()

    app = Application.builder().token(TOKEN).build()

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

    await app.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{host}/webhook" if host else None,
    )

    await app.bot.set_my_commands([
        BotCommand("start", "Iniciar bot"),
        BotCommand("planos", "Planos premium"),
        BotCommand("duvida", "Ajuda"),
        BotCommand("meuid", "Mostrar ID"),
        BotCommand("addpremium", "Adicionar premium (admin)"),
        BotCommand("delpremium", "Remover premium (admin)"),
        BotCommand("verpremium", "Visualizar premium (admin)"),
    ])

    await app.idle()


if __name__ == "__main__":
    asyncio.run(main())
