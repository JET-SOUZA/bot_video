import asyncio
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests

# ===========================
# CONFIGURAÇÕES
# ===========================
TOKEN = "8249697837:AAGfvejL5PT9w8sSPMZnIwErh0jX-XMpAPE"
ADMIN_ID = 5593153639

ASAAS_API_KEY = "$aact_prod_000MzkwODA2MWY2OGM3MWRlMDU2NWM3MzJlNzZmNGZhZGY6OjQxNTY4M2IzLTU1M2UtNGEyNS05ODQ5LTUzM2Q1OTBiYzdiZTo6JGFhY2hfNGU1ZmE3OGEtMzliNS00OTZlLWFmMGMtNDMzN2VlMzM1Yjlh"
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

bot = Bot(token=TOKEN)
app = Flask(__name__)

# ===========================
# FUNÇÕES DO ASAAS
# ===========================
def get_meus_pagamentos(telegram_id):
    url = f"{ASAAS_BASE_URL}/payments?customer={telegram_id}"
    headers = {"access_token": ASAAS_API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        pagamentos = data.get("data", [])
        if pagamentos:
            return "\n".join(
                [f"ID: {p['id']} | Valor: {p['value'] / 100:.2f} | Status: {p['status']}" for p in pagamentos]
            )
        else:
            return "Nenhum pagamento encontrado."
    return "Erro ao consultar pagamentos."

# ===========================
# COMANDOS DO BOT
# ===========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Olá {update.message.from_user.first_name}! 🤖\n"
        "Eu sou seu bot de pagamentos Asaas.\n"
        "Use /meus_pagamentos para ver seus pagamentos."
    )

async def meus_pagamentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pagamentos = get_meus_pagamentos(update.message.from_user.id)
    await update.message.reply_text(pagamentos)

# ===========================
# ROTA DE TESTE
# ===========================
@app.route("/")
def index():
    return "🤖 Bot ativo!", 200

# ===========================
# WEBHOOK DO TELEGRAM
# ===========================
@app.route("/webhook_telegram", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(), bot)
    asyncio.run_coroutine_threadsafe(bot_app.process_update(update), bot_app.loop)
    return jsonify({"status": "ok"}), 200

# ===========================
# INICIALIZAÇÃO DO BOT
# ===========================
bot_app = ApplicationBuilder().token(TOKEN).build()
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("meus_pagamentos", meus_pagamentos))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
