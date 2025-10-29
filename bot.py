# Jet_TikTokShop Bot v4.5 - Adaptado para Render
# Downloads + Premium Dinâmico via Asaas + Ver ID + TikTok com cookies
# Webhook Telegram + Asaas + Flask

import os, json, aiohttp, asyncio, traceback
from datetime import datetime, date
from pathlib import Path
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# -----------------------
# Configurações
# -----------------------
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

ARQUIVO_CONTADOR = "downloads.json"
ARQUIVO_PREMIUM = "premium.json"

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

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
# IDs Premium fixos
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
# Flask Webhook
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/health", methods=["GET"])
def health_check():
    return "Bot ativo!", 200

@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    data = request.json
    status = data.get("status")
    telegram_id = int(data.get("metadata", {}).get("telegram_id", 0))

    if telegram_id == 0:
        return "No telegram ID", 400

    if status == "CONFIRMED":
        USUARIOS_PREMIUM.add(telegram_id)
        salvar_premium(USUARIOS_PREMIUM)
    elif status in ["CANCELED", "EXPIRED"]:
        USUARIOS_PREMIUM.discard(telegram_id)
        salvar_premium(USUARIOS_PREMIUM)

    return "OK", 200

# Telegram Application será inicializado globalmente
app = ApplicationBuilder().token(TOKEN).build()

@flask_app.route(f"/webhook_telegram", methods=["POST"])
def webhook_telegram():
    """Recebe updates do Telegram via webhook."""
    update = Update.de_json(request.get_json(), app.bot)
    asyncio.create_task(app.update_queue.put(update))
    return "OK", 200

# -----------------------
# Comandos Bot
# -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = (
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        "⚠️ Usuário Free: até *10 vídeos/dia*\n"
        "💎 Premium: downloads ilimitados (R$ 9,90/mês).\n\n"
        "✨ Use /planos para assinar Premium."
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown")

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
    await update.message.reply_text(
        "💎 Clique no botão abaixo para pagar a assinatura Premium e liberar downloads ilimitados.",
        reply_markup=markup
    )

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{update.message.from_user.id}`", parse_mode="Markdown")

# -----------------------
# Comandos Admin
# -----------------------
async def premiumadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return
    user_id = int(context.args[0])
    USUARIOS_PREMIUM.add(user_id)
    salvar_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"✅ Usuário {user_id} adicionado como Premium.")

async def premiumdel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return
    user_id = int(context.args[0])
    USUARIOS_PREMIUM.discard(user_id)
    salvar_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"🗑️ Usuário {user_id} removido do Premium.")

async def premiumlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    lista = "\n".join(f"• {uid}" for uid in USUARIOS_PREMIUM)
    await update.message.reply_text(f"💎 Usuários Premium:\n{lista}")

# -----------------------
# Handler para baixar vídeos
# -----------------------
import yt_dlp

async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.message.from_user.id

    if not texto.startswith("http"):
        await update.message.reply_text("❌ Envie um link válido de vídeo.")
        return

    if user_id not in USUARIOS_PREMIUM:
        usados = verificar_limite(user_id)
        if usados >= LIMITE_DIARIO:
            await update.message.reply_text("⚠️ Você atingiu seu limite diário de downloads. Assine o Premium!")
            return

    await update.message.reply_text("⏳ Preparando download...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        out_template = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")
        ydl_opts = {"outtmpl": out_template, "format": "bestvideo+bestaudio/best",
                    "merge_output_format": "mp4", "noplaylist": True, "ignoreerrors": True}

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        filename = await loop.run_in_executor(None, lambda: run_ydl(texto))

        if not os.path.exists(filename):
            await update.message.reply_text("⚠️ Não foi possível localizar o arquivo baixado.")
            return

        tamanho_mb = os.path.getsize(filename) / 1024 / 1024
        with open(filename, "rb") as f:
            if tamanho_mb > 50:
                await update.message.reply_document(f, caption="✅ Aqui está seu vídeo (documento).")
            else:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo em alta qualidade!")

        os.remove(filename)

        if user_id not in USUARIOS_PREMIUM:
            novos_usos = incrementar_download(user_id)
            await update.message.reply_text(f"📊 Uso diário: *{novos_usos}/{LIMITE_DIARIO}*", parse_mode="Markdown")

    except Exception as e:
        tb = traceback.format_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")
        print(tb)

# -----------------------
# Registro de handlers
# -----------------------
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("planos", planos))
app.add_handler(CommandHandler("duvida", duvida))
app.add_handler(CommandHandler("meuid", meuid))

app.add_handler(CommandHandler("premiumadd", premiumadd))
app.add_handler(CommandHandler("premiumdel", premiumdel))
app.add_handler(CommandHandler("premiumlist", premiumlist))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

# -----------------------
# Inicialização
# -----------------------
if __name__ == "__main__":
    print("🤖 Bot pronto! Aguardando mensagens via Webhook...")
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
