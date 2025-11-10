# Jet TikTokShop Bot - Arquitetura C + Shopee Patch Absoluto + Safe Input + LOGS
# PTB20 Webhook + Asaas + TikTok

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import yt_dlp
import requests
import os
import json
import asyncio
import traceback
from datetime import datetime, date
from pathlib import Path
from urllib.parse import unquote
import re

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.environ.get("BOT_TOKEN")
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

ADMIN_ID = 5593153639
LIMITE_DIARIO = 10
PORT = int(os.environ.get("PORT", 10000))

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
# JSON UTILS
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
USUARIOS_PREMIUM.add(ADMIN_ID)
save_premium(USUARIOS_PREMIUM)

# -------------------------
# CHECK ASAAS
# -------------------------
def verificar_pagamentos_asaas():
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
# COMMANDS
# -------------------------
async def start(update, context):
    await update.message.reply_text(
        "🎬 *Jet TikTokShop Bot*\n\n"
        "Envie um link de vídeo para baixar.\n"
        "⚠️ Free: 10 downloads/dia\n"
        "💎 Premium: ilimitado",
        parse_mode="Markdown"
    )

async def planos(update, context):
    kb = [
        [InlineKeyboardButton("💎 1 Mês – R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses – R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano – R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")],
    ]
    await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))

async def duvida(update, context):
    await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")

async def meuid(update, context):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")


# -------------------------
# DOWNLOAD + SHOPEE PATCH ABSOLUTO + LOGS
# -------------------------
async def baixar_video(update: Update, context):

    # LOG RAW DO UPDATE
    print("\n================ RAW UPDATE RECEBIDO ================")
    try:
        print(update.to_dict())
    except:
        print("ERRO AO IMPRIMIR UPDATE RAW")
    print("===================================================\n")

    # SAFE GUARD
    if not update.message or not update.message.text:
        return await update.message.reply_text("❌ Não consegui ler o link. Envie novamente.")

    # Captura URL
    url = update.message.text.strip()
    uid = update.message.from_user.id

    # Normalização
    original_url = url
    url = unquote(url).replace("\\/", "/").replace("\u200b", "").strip()

    # LOG
    print(f"URL ORIGINAL: {original_url}")
    print(f"URL NORMALIZADA: {url}")

    # -------------------------
    # SHOPEE PATCH ABSOLUTO
    # -------------------------
    if "shopee.com" in url or "sv.shopee.com" in url:
        await update.message.reply_text("🔄 Resolvendo link da Shopee...")

        try:
            # Tenta extrair ID do share-video direto do link
            m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", url)

            if not m:
                print("ID não achado no link → tentando via HTML…")
                try:
                    html = requests.get(url, timeout=10).text
                    m = re.search(r"https://sv\\.shopee\\.com\\.br/share-video/([A-Za-z0-9=_\-]+)", html)
                except Exception as e:
                    print("Erro ao baixar HTML Shopee:", e)

            if not m:
                print("FALHA: NÃO EXTRAÍ ID DO SHOPEE")
                return await update.message.reply_text("❌ Não consegui extrair o ID da Shopee.")

            share_id = m.group(1)
            print(f"ID EXTRAÍDO → {share_id}")

            # Chamada API real
            api_url = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
            print(f"API SHOPEE URL: {api_url}")

            data = requests.get(api_url, timeout=10).json()
            print("RESPOSTA API SHOPEE:", data)

            video_url = data.get("data", {}).get("video_url")
            if not video_url:
                return await update.message.reply_text("❌ Shopee não retornou o video_url final.")

            url = video_url
            print(f"URL FINAL SHOPEE: {url}")

        except Exception as e:
            print("ERRO SHOPEE PATCH →", e)
            return await update.message.reply_text(f"❌ Erro Shopee: {e}")

    # -----------------------------------------------------------------
    # AGORA SIM – LINK FINAL VALIDADO
    # -----------------------------------------------------------------
    print(f"URL FINAL PARA DOWNLOAD: {url}")

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Link inválido.")

    verificar_pagamentos_asaas()

    if uid not in USUARIOS_PREMIUM:
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    await update.message.reply_text("⏳ Baixando...")

    # -------------------------
    # DOWNLOAD FINAL
    # -------------------------
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        ydl_opts = {
            "outtmpl": output,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
        }

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print("EXECUTANDO YT-DLP COM URL:", url)
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, lambda: run(url))

        with open(file_path, "rb") as f:
            await update.message.reply_video(f, caption="✅ Pronto!")

        os.remove(file_path)

        if uid not in USUARIOS_PREMIUM:
            novo = incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {novo}/{LIMITE_DIARIO}")

    except Exception as e:
        print("YT-DLP ERRO RAW:\n", traceback.format_exc())
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
        url_path="webhook",
        webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/webhook"
    )


if __name__ == "__main__":
    main()
