# ==============================
# Jet_TikTokShop Bot v5.0 (Webhook Edition)
# 24/7 Render + Asaas + Premium Dinâmico + TikTok com Cookies
# ==============================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp
from datetime import datetime, date
from pathlib import Path
import asyncio, traceback
from flask import Flask, request

# -----------------------
# Configurações
# -----------------------
# ⚠️ Corrigido: o token agora está entre aspas ou pode vir do ambiente Render.
TOKEN = os.getenv("BOT_TOKEN", "8249697837:AAGfvejL5PT9w8sSPMZnIwErh0jX-XMpAPE")
ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "$aact_prod_000MzkwODA2MWY2OGM3MWRlMDU2NWM3MzJlNzZmNGZhZGY6OjQxNTY4M2IzLTU1M2UtNGEyNS05ODQ5LTUzM2Q1OTBiYzdiZTo6JGFhY2hfNGU1ZmE3OGEtMzliNS00OTZlLWFmMGMtNDMzN2VlMzM1Yjlh")
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
USUARIOS_PREMIUM.update({ADMIN_ID})
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
    mensagem = (
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        "⚠️ Usuário Free: até *10 vídeos/dia*\n"
        "💎 Premium: downloads ilimitados (R$ 9,90/mês).\n\n"
        "✨ Use o botão de menu (📎 ➜ /) para ver os comandos disponíveis."
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

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

    keyboard = [[InlineKeyboardButton("💰 Pagar Premium", url=link_pagamento)]]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💎 Clique no botão abaixo para pagar sua assinatura Premium:", reply_markup=markup)

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{user_id}`", parse_mode="Markdown")

# -----------------------
# Download
# -----------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.message.from_user.id

    if not texto.startswith("http"):
        await update.message.reply_text("❌ Envie um link válido de vídeo.")
        return

    if user_id not in USUARIOS_PREMIUM:
        usados = verificar_limite(user_id)
        if usados >= LIMITE_DIARIO:
            await update.message.reply_text("⚠️ Limite diário atingido! Assine o Premium para uso ilimitado.")
            return

    await update.message.reply_text("⏳ Baixando vídeo... aguarde.")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        out_template = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        ydl_opts = {
            "outtmpl": out_template,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "ignoreerrors": True,
            "geo_bypass": True,
            "retries": 3,
            "no_warnings": True
        }

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))

        candidato = ydl_obj.prepare_filename(info)
        if not candidato or not os.path.exists(candidato):
            await update.message.reply_text("⚠️ Não consegui localizar o vídeo.")
            return

        tamanho_mb = os.path.getsize(candidato) / 1024 / 1024
        with open(candidato, "rb") as f:
            if tamanho_mb > 50:
                await update.message.reply_document(f, caption="✅ Seu vídeo (enviado como arquivo).")
            else:
                await update.message.reply_video(f, caption="✅ Seu vídeo está aqui!")

        os.remove(candidato)

        if user_id not in USUARIOS_PREMIUM:
            novos_usos = incrementar_download(user_id)
            await update.message.reply_text(f"📊 Uso diário: {novos_usos}/{LIMITE_DIARIO}")

    except Exception as e:
        tb = traceback.format_exc()
        await update.message.reply_text(f"❌ Erro: {e}")
        print(tb)

# -----------------------
# Webhook ASAAS
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    data = request.json
    status = data.get("status")
    telegram_id = int(data.get("metadata", {}).get("telegram_id", 0))
    if telegram_id == 0:
        return "No Telegram ID", 400

    if status == "CONFIRMED":
        USUARIOS_PREMIUM.add(telegram_id)
        salvar_premium(USUARIOS_PREMIUM)
        print(f"✅ Premium liberado para ID {telegram_id}")
    elif status in ["CANCELED", "EXPIRED"]:
        if telegram_id in USUARIOS_PREMIUM:
            USUARIOS_PREMIUM.remove(telegram_id)
            salvar_premium(USUARIOS_PREMIUM)
        print(f"⚠️ Premium removido para ID {telegram_id}")
    return "OK", 200

# -----------------------
# Inicialização via Webhook (Render)
# -----------------------
WEBHOOK_URL = "https://bot-video-mgli.onrender.com/webhook_telegram"

async def init_bot():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("planos", planos))
    application.add_handler(CommandHandler("duvida", duvida))
    application.add_handler(CommandHandler("meuid", meuid))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    await application.bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Webhook configurado com sucesso!")
    return application

bot_app = asyncio.get_event_loop().run_until_complete(init_bot())

@flask_app.route("/")
def home():
    return "🤖 Bot Jet_TikTokShop ativo no Render!"

@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    try:
        update = Update.model_validate(request.get_json(force=True))
        asyncio.get_event_loop().create_task(bot_app.update_queue.put(update))
    except Exception as e:
        print("❌ Erro no webhook:", e)
        return "ERROR", 500
    return "OK", 200



if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))


