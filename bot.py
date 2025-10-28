# ==============================
# Jet_TikTokShop Bot v6.0 (Render Webhook Stable)
# ==============================

import os, json, asyncio, traceback
from datetime import datetime, date
from pathlib import Path
import yt_dlp, aiohttp
import nest_asyncio
nest_asyncio.apply()

from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# -----------------------
# Configurações
# -----------------------
TOKEN = "8249697837:AAGfvejL5PT9w8sSPMZnIwErh0jX-XMpAPE"
WEBHOOK_URL = "https://bot-video-mgli.onrender.com/webhook_telegram"

ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

ASAAS_API_KEY = "$aact_prod_000MzkwODA2MWY2OGM3MWRlMDU2NWM3MzJlNzZmNGZhZGY6OjQxNTY4M2IzLTU1M2UtNGEyNS05ODQ5LTUzM2Q1OTBiYzdiZTo6JGFhY2hfNGU1ZmE3OGEtMzliNS00OTZlLWFmMGMtNDMzN2VlMzM1Yjlh"
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

ARQUIVO_CONTADOR = "downloads.json"
ARQUIVO_PREMIUM = "premium.json"

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

# -----------------------
# Funções JSON
# -----------------------
def carregar_json(caminho):
    if os.path.exists(caminho):
        with open(caminho, "r") as f:
            return json.load(f)
    return {}

def salvar_json(caminho, dados):
    with open(caminho, "w") as f:
        json.dump(dados, f)

# -----------------------
# Premium
# -----------------------
def carregar_premium():
    dados = carregar_json(ARQUIVO_PREMIUM)
    return set(map(int, dados.get("premium_users", [])))

def salvar_premium(usuarios):
    salvar_json(ARQUIVO_PREMIUM, {"premium_users": list(usuarios)})

USUARIOS_PREMIUM = carregar_premium()
USUARIOS_PREMIUM.add(ADMIN_ID)
salvar_premium(USUARIOS_PREMIUM)

# -----------------------
# Limite diário
# -----------------------
def verificar_limite(user_id):
    dados = carregar_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(user_id) not in dados or dados[str(user_id)]["data"] != hoje:
        dados[str(user_id)] = {"data": hoje, "downloads": 0}
        salvar_json(ARQUIVO_CONTADOR, dados)
    return dados[str(user_id)]["downloads"]

def incrementar_download(user_id):
    dados = carregar_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(user_id) not in dados or dados[str(user_id)]["data"] != hoje:
        dados[str(user_id)] = {"data": hoje, "downloads": 1}
    else:
        dados[str(user_id)]["downloads"] += 1
    salvar_json(ARQUIVO_CONTADOR, dados)
    return dados[str(user_id)]["downloads"]

# -----------------------
# Comandos
# -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        "⚠️ Usuário Free: até *10 vídeos/dia*\n"
        "💎 Premium: downloads ilimitados (R$ 9,90/mês)."
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    async with aiohttp.ClientSession() as session:
        payload = {
            "customer": "CUS_ID_DO_CLIENTE",
            "billingType": "PIX",
            "value": 9.90,
            "dueDate": datetime.now().strftime("%Y-%m-%d"),
            "description": "Assinatura Premium Jet_TikTokShop",
            "metadata": {"telegram_id": user_id}
        }
        headers = {"access_token": ASAAS_API_KEY, "Content-Type": "application/json"}
        async with session.post(f"{ASAAS_BASE_URL}/payments", json=payload, headers=headers) as resp:
            data = await resp.json()
            link_pagamento = data.get("pixQrCode") or data.get("paymentLink") or "https://www.asaas.com"
    teclado = [[InlineKeyboardButton("💰 Pagar Premium", url=link_pagamento)]]
    await update.message.reply_text("💎 Clique abaixo para pagar:", reply_markup=InlineKeyboardMarkup(teclado))

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: `{update.effective_user.id}`", parse_mode="Markdown")

# -----------------------
# Download
# -----------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.message.from_user.id

    if not texto.startswith("http"):
        await update.message.reply_text("❌ Envie um link válido.")
        return

    if user_id not in USUARIOS_PREMIUM:
        usados = verificar_limite(user_id)
        if usados >= LIMITE_DIARIO:
            await update.message.reply_text("⚠️ Limite diário atingido.")
            return

    await update.message.reply_text("⏳ Baixando vídeo...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        out_template = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")
        ydl_opts = {
            "outtmpl": out_template,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "ignoreerrors": True
        }
        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def baixar(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        arquivo = await loop.run_in_executor(None, lambda: baixar(texto))
        if not os.path.exists(arquivo):
            await update.message.reply_text("⚠️ Falha ao baixar o vídeo.")
            return

        tamanho = os.path.getsize(arquivo) / 1024 / 1024
        with open(arquivo, "rb") as f:
            if tamanho > 50:
                await update.message.reply_document(f, caption="✅ Seu vídeo (documento).")
            else:
                await update.message.reply_video(f, caption="✅ Seu vídeo!")

        os.remove(arquivo)

        if user_id not in USUARIOS_PREMIUM:
            usados = incrementar_download(user_id)
            await update.message.reply_text(f"📊 {usados}/{LIMITE_DIARIO} downloads hoje.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")
        print(traceback.format_exc())

# -----------------------
# Inicialização global
# -----------------------
flask_app = Flask(__name__)
bot_app = None  # será definido após inicialização

@flask_app.route("/")
def home():
    return "🤖 Bot ativo no Render!"

@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    global bot_app
    if bot_app is None:
        return "Bot não inicializado ainda", 503

    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot_app.bot)
        asyncio.create_task(bot_app.process_update(update))
    except Exception as e:
        print("❌ Erro no webhook:", e)
        print(traceback.format_exc())
        return "Erro interno", 500

    return "OK", 200

# -----------------------
# Main
# -----------------------
async def iniciar_bot():
    global bot_app
    bot_app = ApplicationBuilder().token(TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("planos", planos))
    bot_app.add_handler(CommandHandler("duvida", duvida))
    bot_app.add_handler(CommandHandler("meuid", meuid))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    await bot_app.bot.set_webhook(WEBHOOK_URL)
    print("✅ Webhook configurado:", WEBHOOK_URL)

    await bot_app.initialize()
    await bot_app.start()
    print("🤖 Bot iniciado e pronto!")

async def main():
    await iniciar_bot()
    port = int(os.environ.get("PORT", 5000))
    await asyncio.to_thread(lambda: flask_app.run(host="0.0.0.0", port=port, use_reloader=False))

if __name__ == "__main__":
    asyncio.run(main())



