# Jet_TikTokShop Bot v4.6 - Premium via Asaas + QR Code PIX + Vencimento Automático + Webhook
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask, request
from datetime import datetime, timedelta
import asyncio, os, json, aiohttp
from io import BytesIO
import threading

# -----------------------
# CONFIGURAÇÕES
# -----------------------
ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "SUA_CHAVE_API_ASAAS_AQUI")
ASAAS_API_URL = "https://www.asaas.com/api/v3"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

USUARIOS_PREMIUM = {}  # {telegram_id: {"vencimento": date, "plano": "1m"}}

def salvar_premium(usuarios):
    with open("usuarios_premium.json", "w") as f:
        json.dump(usuarios, f)

def carregar_premium():
    global USUARIOS_PREMIUM
    if os.path.exists("usuarios_premium.json"):
        with open("usuarios_premium.json", "r") as f:
            USUARIOS_PREMIUM = json.load(f)
    else:
        USUARIOS_PREMIUM = {}

carregar_premium()

# -----------------------
# TELEGRAM BOT
# -----------------------
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botoes = [
        [InlineKeyboardButton("💎 1 Mês - R$ 9,90", callback_data="plano_1m")],
        [InlineKeyboardButton("💎 3 Meses - R$ 25,90", callback_data="plano_3m")],
        [InlineKeyboardButton("💎 1 Ano - R$ 89,90", callback_data="plano_1a")],
    ]
    markup = InlineKeyboardMarkup(botoes)
    await update.message.reply_text(
        "💎 Escolha seu plano Premium para liberar downloads ilimitados:",
        reply_markup=markup,
    )

async def callback_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    links_planos = {
        "plano_1m": {"descricao": "1 Mês", "valor": 9.90, "url": "https://www.asaas.com/c/knu5vub6ejc2yyja"},
        "plano_3m": {"descricao": "3 Meses", "valor": 25.90, "url": "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"},
        "plano_1a": {"descricao": "1 Ano", "valor": 89.90, "url": "https://www.asaas.com/c/puto9coszhwgprqc"},
    }

    plano = links_planos.get(query.data)
    if not plano:
        await query.edit_message_text("Plano inválido.")
        return

    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={plano['url']}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(qr_url) as resp:
            img_data = await resp.read()
    
    bio = BytesIO(img_data)
    bio.name = "qrcode.png"
    await query.message.reply_photo(
        photo=InputFile(bio),
        caption=f"💎 Plano: {plano['descricao']}\n💰 Valor: R$ {plano['valor']}\n\n"
                f"👉 Pague via PIX escaneando o QR Code ou clicando no link:\n{plano['url']}"
    )

app.add_handler(CommandHandler("planos", planos))
app.add_handler(CallbackQueryHandler(callback_planos, pattern="^plano_"))

# -----------------------
# VERIFICAÇÃO DE VENCIMENTOS
# -----------------------
async def verificar_vencimentos():
    while True:
        hoje = datetime.now().date()
        for user_id, info in list(USUARIOS_PREMIUM.items()):
            venc = datetime.strptime(info["vencimento"], "%Y-%m-%d").date()
            dias_restantes = (venc - hoje).days
            if dias_restantes == 1:
                await app.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Seu plano Premium vence amanhã! Renove para continuar com acesso ilimitado."
                )
            elif dias_restantes == 0:
                await app.bot.send_message(
                    chat_id=user_id,
                    text="❌ Seu plano Premium venceu hoje. Renove para continuar aproveitando o bot!"
                )
        await asyncio.sleep(86400)

# -----------------------
# FLASK (Webhook Asaas + Telegram + Health)
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    data = request.json
    status = data.get("status")
    telegram_id = int(data.get("metadata", {}).get("telegram_id", 0))
    if telegram_id == 0:
        return "No telegram ID", 400

    planos = {
        "1 Mês": 30,
        "3 Meses": 90,
        "1 Ano": 365,
    }

    if status == "CONFIRMED":
        descricao = data.get("description", "1 Mês")
        dias = planos.get(descricao, 30)
        vencimento = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
        USUARIOS_PREMIUM[telegram_id] = {"vencimento": vencimento, "plano": descricao}
        salvar_premium(USUARIOS_PREMIUM)
    elif status in ["CANCELED", "EXPIRED"]:
        if str(telegram_id) in USUARIOS_PREMIUM:
            del USUARIOS_PREMIUM[str(telegram_id)]
            salvar_premium(USUARIOS_PREMIUM)
    return "OK", 200

@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    from telegram import Update
    update = Update.de_json(request.get_json(force=True), app.bot)
    app.update_queue.put(update)
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# -----------------------
# EXECUÇÃO
# -----------------------
if __name__ == "__main__":
    # Inicia Flask
    threading.Thread(target=run_flask).start()
    # Inicia verificação de vencimentos
    asyncio.get_event_loop().create_task(verificar_vencimentos())
    print("Bot pronto para receber mensagens via Webhook!")
