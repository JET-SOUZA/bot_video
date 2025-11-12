# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + yt-dlp
# Atualização 2025-11: fixes mobile streaming (faststart + streaming flag) + premium

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
# ADMIN COMANDOS MANUAIS
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
# SHOPEE UNIVERSAL PATCH 2025
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
        or (data.get("data", {}).get("videos", [{}])[0].get("url")
            if data.get("data", {}).get("videos") else None)
        or data.get("data", {}).get("path")
    )
    if not video_url:
        try:
            html = requests.get(url, timeout=10).text
            mp4 = re.search(r"https?://[^\s\"']+\.mp4", html)
            if mp4:
                return mp4.group(0)
            m3u8 = re.search(r"https?://[^\s\"']+\.m3u8[^\s\"']*", html)
            if m3u8:
                return m3u8.group(0)
            json_url = re.search(r'"url":"(https:[^"]+)"', html)
            if json_url:
                return json_url.group(1)
            json_play = re.search(r'"play[^"]*":"(https:[^"]+)"', html)
            if json_play:
                return json_play.group(1)
        except:
            pass
    return video_url

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

    if "shopee.com" in url or "shp.ee" in url or "sv.shopee.com" in url:
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo.")
        url = video_url

    await update.message.reply_text("⏳ Baixando...")
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        # Adiciona faststart para mp4 mobile-friendly
        ydl_opts = {
            "outtmpl": output,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "postprocessor_args": ["-movflags", "faststart"],  # <<-- chave para mobile
        }
        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, lambda: run(url))

        # Aguarda microtempo para o sistema de arquivos liberar o merge (reduz risco de arquivo truncado)
        await asyncio.sleep(0.5)

        # Garantir que o arquivo existe e tem tamanho razoável
        if not os.path.exists(file_path) or os.path.getsize(file_path) < 1024:
            # fallback: tenta enviar como documento se vídeo parece inválido
            await update.message.reply_text("❌ Erro: arquivo final inválido ou muito pequeno.")
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            return

        # Envia explicitamente como video com streaming support (melhora reprodução mobile)
        with open(file_path, "rb") as f:
            await update.message.reply_video(f, caption="✅ Seu vídeo está aqui!", supports_streaming=True)

        # remove
        try:
            os.remove(file_path)
        except:
            pass

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

    # run_webhook em PTB20 espera ser awaited
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("HOSTNAME") or f"localhost:{PORT}"
    webhook_url = f"https://{hostname}/webhook"
    print(f"Iniciando bot (webhook) na porta {PORT}, webhook_url={webhook_url}")

    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=webhook_url
    )

if __name__ == "__main__":
    asyncio.run(main())
