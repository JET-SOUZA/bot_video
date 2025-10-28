import os
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==========================
# CONFIGURAÇÕES
# ==========================
TOKEN = os.environ.get("TELEGRAM_TOKEN")  # seu token do bot
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # ex: https://seu-app.onrender.com/webhook_telegram
ADMIN_ID = 5593153639  # seu ID de admin

# Exemplo de banco de dados em memória
USERS = {
    # user_id: {"plano": "premium", "vencimento": "2025-10-31"}
}

# Flask
flask_app = Flask(__name__)

# ==========================
# HANDLERS DO TELEGRAM
# ==========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Seu bot está ativo.")

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"Seu plano: {USERS.get(user_id, {}).get('plano', 'Nenhum')}")

# ==========================
# TASK DE NOTIFICAÇÃO
# ==========================
async def expirations_watcher():
    while True:
        now = datetime.now()
        for user_id, data in USERS.items():
            vencimento = datetime.strptime(data["vencimento"], "%Y-%m-%d")
            dias_para_vencer = (vencimento - now).days

            try:
                if dias_para_vencer == 3:
                    await app.bot.send_message(user_id, "Seu plano vence em 3 dias!")
                elif dias_para_vencer == 1:
                    await app.bot.send_message(user_id, "Seu plano vence amanhã!")
                elif dias_para_vencer == 0:
                    await app.bot.send_message(user_id, "Seu plano vence hoje!")
            except Exception as e:
                await app.bot.send_message(ADMIN_ID, f"Erro notificando {user_id}: {e}")

        await asyncio.sleep(60 * 60)  # roda a cada 1 hora

# ==========================
# WEBHOOK FLASK
# ==========================
@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    data = request.get_json(force=True)
    update = Update.de_json(data, app.bot)
    app.update_queue.put_nowait(update)
    return "OK", 200

# ==========================
# INICIALIZAÇÃO DO BOT
# ==========================
async def start_app():
    global app
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))

    # Inicializa bot
    await app.initialize()
    await app.start()

    # Configura webhook
    await app.bot.set_webhook(WEBHOOK_URL)

    # Inicia watcher de expiração
    asyncio.create_task(expirations_watcher())

# ==========================
# FLASK + LOOP ASYNC
# ==========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    loop = asyncio.get_event_loop()
    loop.create_task(start_app())

    flask_app.run(host="0.0.0.0", port=port)
