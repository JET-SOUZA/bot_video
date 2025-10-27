# ============================== 
# Jet_TikTokShop Bot v4.5
# Downloads + Premium Dinâmico via Asaas + Ver ID (menu) + TikTok com cookies
# ==============================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp
from datetime import datetime, date
from pathlib import Path
import asyncio, traceback
from flask import Flask, request
import threading

# -----------------------
# Configurações
# -----------------------
TOKEN = "8249697837:AAGfvejL5PT9w8sSPMZnIwErh0jX-XMpAPE"
ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

ASAAS_API_KEY = "$aact_prod_000MzkwODA2MWY2OGM3MWRlMDU2NWM3MzJlNzZmNGZhZGY6OjQxNTY4M2IzLTU1M2UtNGEyNS05ODQ5LTUzM2Q1OTBiYzdiZTo6JGFhY2hfNGU1ZmE3OGEtMzliNS00OTZlLWFmMGMtNDMzN2VlMzM1Yjlh"
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

ARQUIVO_CONTADOR = "downloads.json"
ARQUIVO_PREMIUM = "premium.json"

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Caminho do arquivo de cookies do TikTok
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

# IDs Premium fixos
ID_PREMIUM_1 = 5593153639
ID_PREMIUM_2 = 0
ID_PREMIUM_3 = 0
ID_PREMIUM_4 = 0

USUARIOS_PREMIUM.update({ID_PREMIUM_1, ID_PREMIUM_2, ID_PREMIUM_3, ID_PREMIUM_4})
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
# Comandos do bot
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
    texto = "💎 Clique no botão abaixo para pagar a assinatura Premium e liberar downloads ilimitados."
    await update.message.reply_text(texto, reply_markup=markup)

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com", parse_mode="Markdown")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{user_id}`", parse_mode="Markdown")

# -----------------------
# Download de vídeo
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
            await update.message.reply_text("⚠️ Você atingiu seu limite diário de downloads. Assine o Premium para uso ilimitado!")
            return

    await update.message.reply_text("⏳ Preparando download...", parse_mode="Markdown")

    try:
        # Resolver links curtos
        if "pin.it/" in texto:
            async with aiohttp.ClientSession() as session:
                async with session.get(texto, allow_redirects=True) as resp:
                    texto = str(resp.url)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        out_template = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        ydl_opts = {
            "outtmpl": out_template,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "ignoreerrors": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "retries": 3,
            "no_warnings": True
        }

        # TikTok cookies
        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))

        try:
            candidato = ydl_obj.prepare_filename(info)
        except Exception:
            arquivos = sorted(DOWNLOADS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            candidato = str(arquivos[0]) if arquivos else None

        if not candidato or not os.path.exists(candidato):
            await update.message.reply_text("⚠️ Não foi possível localizar o arquivo baixado.")
            return

        tamanho_mb = os.path.getsize(candidato) / 1024 / 1024
        with open(candidato, "rb") as f:
            if tamanho_mb > 50:
                await update.message.reply_document(f, caption="✅ Aqui está seu vídeo (documento).")
            else:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo em alta qualidade!")

        os.remove(candidato)

        if user_id not in USUARIOS_PREMIUM:
            novos_usos = incrementar_download(user_id)
            await update.message.reply_text(f"📊 Uso diário: *{novos_usos}/{LIMITE_DIARIO}*", parse_mode="Markdown")

    except Exception as e:
        tb = traceback.format_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")
        print(tb)

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
    if user_id in USUARIOS_PREMIUM:
        USUARIOS_PREMIUM.remove(user_id)
        salvar_premium(USUARIOS_PREMIUM)
        await update.message.reply_text(f"🗑️ Usuário {user_id} removido do Premium.")

async def premiumlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    lista = "\n".join(f"• {uid}" for uid in USUARIOS_PREMIUM)
    await update.message.reply_text(f"💎 Usuários Premium:\n{lista}")

# -----------------------
# Webhook Flask Asaas
# -----------------------
flask_app = Flask(__name__)

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
        if telegram_id in USUARIOS_PREMIUM:
            USUARIOS_PREMIUM.remove(telegram_id)
            salvar_premium(USUARIOS_PREMIUM)
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))  # Usa porta do Render ou default 5000
    flask_app.run(host="0.0.0.0", port=port)

# -----------------------
# Inicialização (compatível Render/PTB v20+)
# -----------------------
def main():
    threading.Thread(target=run_flask, daemon=True).start()

    async def comandos_post_init(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Iniciar o bot"),
            BotCommand("planos", "Ver planos Premium"),
            BotCommand("duvida", "Ajuda e contato"),
            BotCommand("meuid", "Ver seu ID do Telegram")
        ])

    async def run_bot():
        app = ApplicationBuilder().token(TOKEN).post_init(comandos_post_init).build()

        # Comandos principais
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("planos", planos))
        app.add_handler(CommandHandler("duvida", duvida))
        app.add_handler(CommandHandler("meuid", meuid))

        # Admin
        app.add_handler(CommandHandler("premiumadd", premiumadd))
        app.add_handler(CommandHandler("premiumdel", premiumdel))
        app.add_handler(CommandHandler("premiumlist", premiumlist))

        # Mensagens com links
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

        print("🤖 Bot iniciado... aguardando mensagens.")
        await app.run_polling()

    try:
        asyncio.run(run_bot())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(run_bot())
        loop.run_forever()

if __name__ == "__main__":
    main()
