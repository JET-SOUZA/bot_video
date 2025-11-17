# Jet TikTokShop Bot - Arquitetura C (Render + Webhook)
# PTB20 + yt-dlp 2025 + Shopee Universal Patch + Instagram Cookies B64
# Revisão completa 2025-11

import os
import json
import asyncio
import base64
import requests
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import yt_dlp


# ===============================================================
# CONFIGURAÇÕES
# ===============================================================

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

ARQ_PREMIUM = DATA_DIR / "premium.json"
ARQ_CONTADOR = DATA_DIR / "contador.json"
COOKIES_INSTAGRAM = DATA_DIR / "cookies_ig.txt"

USUARIOS_PREMIUM = set()
CONTADOR = {}


# ===============================================================
# CARREGAR BASES LOCAIS
# ===============================================================

def carregar_arquivos():
    global USUARIOS_PREMIUM, CONTADOR

    if ARQ_PREMIUM.exists():
        USUARIOS_PREMIUM = set(json.load(open(ARQ_PREMIUM, "r")))

    if ARQ_CONTADOR.exists():
        CONTADOR = json.load(open(ARQ_CONTADOR, "r"))


def salvar_premium():
    json.dump(list(USUARIOS_PREMIUM), open(ARQ_PREMIUM, "w"))


def salvar_contador():
    json.dump(CONTADOR, open(ARQ_CONTADOR, "w"))


carregar_arquivos()


# ===============================================================
# COOKIES INSTAGRAM via BASE64
# ===============================================================

if os.getenv("COOKIES_IG_B64"):
    try:
        decoded = base64.b64decode(os.getenv("COOKIES_IG_B64")).decode("utf-8")
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(decoded)
        print("Cookies Instagram carregados com sucesso!")
    except Exception as e:
        print("Erro ao decodificar COOKIES_IG_B64:", e)


# ===============================================================
# FUNÇÃO: EXTRATOR INSTAGRAM
# ===============================================================

async def extrair_instagram(url: str):
    ydl_opts = {
        "quiet": True,
        "format": "best[ext=mp4]/best",
        "skip_download": True,
        "nocheckcertificate": True,
        "cookiefile": str(COOKIES_INSTAGRAM) if COOKIES_INSTAGRAM.exists() else None,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("url")


# ===============================================================
# FUNÇÃO: EXTRATOR SHOPEE
# ===============================================================

async def extrair_shopee(url: str):
    # Corrigido para Shopee 2025 universal-link
    if "share-video" in url:
        try:
            ydl_opts = {
                "quiet": True,
                "format": "best[ext=mp4]/best",
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get("url")
        except:
            return None
    return None


# ===============================================================
# CONTADOR DIÁRIO
# ===============================================================

def adicionar_download(user_id: int):
    from datetime import datetime
    dia = datetime.now().strftime("%Y-%m-%d")

    if str(user_id) not in CONTADOR:
        CONTADOR[str(user_id)] = {}

    hoje = CONTADOR[str(user_id)].get(dia, 0)

    CONTADOR[str(user_id)][dia] = hoje + 1
    salvar_contador()


def checar_limite(user_id: int):
    from datetime import datetime
    dia = datetime.now().strftime("%Y-%m-%d")

    if str(user_id) not in CONTADOR:
        return 0

    return CONTADOR[str(user_id)].get(dia, 0)


# ===============================================================
# COMANDO: /start
# ===============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📥 Baixar Vídeo", callback_data="baixar")],
        [InlineKeyboardButton("💎 Comprar Premium", callback_data="premium")],
    ]

    await update.message.reply_text(
        "👋 Bem-vindo! Envie qualquer link do TikTok, Instagram ou Shopee.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ===============================================================
# COMANDOS ADMIN: ADD E REMOVER PREMIUM
# ===============================================================

async def addpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas admin.")

    if not context.args:
        return await update.message.reply_text("Use: /addpremium ID")

    uid = int(context.args[0])
    USUARIOS_PREMIUM.add(uid)
    salvar_premium()

    await update.message.reply_text(f"Usuário {uid} adicionado ao premium.")


async def delpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas admin.")

    if not context.args:
        return await update.message.reply_text("Use: /delpremium ID")

    uid = int(context.args[0])
    USUARIOS_PREMIUM.discard(uid)
    salvar_premium()

    await update.message.reply_text(f"Usuário {uid} removido do premium.")


# ===============================================================
# COMANDO NOVO: /verpremium
# ===============================================================

async def verpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas admin.")

    if not USUARIOS_PREMIUM:
        return await update.message.reply_text("Nenhum premium cadastrado.")

    texto = "💎 Lista Premium:\n" + "\n".join(str(x) for x in USUARIOS_PREMIUM)
    await update.message.reply_text(texto)


# ===============================================================
# PROCESSAMENTO DE LINKS
# ===============================================================

async def receber_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.message.from_user.id

    # Verificar limite diário
    if user_id not in USUARIOS_PREMIUM:
        usados = checar_limite(user_id)
        if usados >= 10:
            return await update.message.reply_text(
                "🚫 Você atingiu o limite diário (10 downloads por dia)."
            )

    try:
        if "instagram" in url:
            final = await extrair_instagram(url)

        elif "shopee" in url:
            final = await extrair_shopee(url)

        else:
            final = None

        if not final:
            return await update.message.reply_text("❌ Não consegui extrair esse link.")

        adicionar_download(user_id)

        await update.message.reply_video(final)

    except Exception as e:
        await update.message.reply_text(f"Erro: {e}")


# ===============================================================
# KEEP ALIVE (Render Cold Start fix)
# ===============================================================

async def ping():
    await asyncio.sleep(5)
    while True:
        try:
            host = os.getenv("RENDER_EXTERNAL_HOSTNAME")
            if host:
                requests.get(f"https://{host}/webhook")
        except:
            pass
        await asyncio.sleep(300)


# ===============================================================
# MAIN
# ===============================================================

async def main():
    app = Application.builder().token(TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(CommandHandler("verpremium", verpremium))

    # Mensagens de link
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_link))

    # Keep Alive
    asyncio.create_task(ping())

    # Config Webhook
    host = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    await app.bot.set_my_commands([
        BotCommand("start", "Iniciar"),
        BotCommand("addpremium", "Adicionar premium"),
        BotCommand("delpremium", "Remover premium"),
        BotCommand("verpremium", "Ver premium"),
    ])

    await app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        secret_token=None,
        url_path="webhook",
        webhook_url=f"https://{host}/webhook",
    )


if __name__ == "__main__":
    asyncio.run(main())
