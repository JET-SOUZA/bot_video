import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------- CONFIGURAÇÃO -------------------
TOKEN = "8249697837:AAGfvejL5PT9w8sSPMZnIwErh0jX-XMpAPE"
ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

ASAAS_API_KEY = "$aact_prod_000MzkwODA2MWY2OGM3MWRlMDU2NWM3MzJlNzZmNGZhZGY6OmE2MTJlYWY3LWUyYWItNGJmNS05YjNmLWFiMTI3Mzc2NjMwZDo6JGFhY2hfZTIzNDcwY2MtNjI1Ni00NGQ3LTlhODgtNWYzZTFmNzM5YmY0"
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

WEBHOOK_URL = "https://bot-video-mgli.onrender.com/webhook_telegram"  # Substitua pelo seu URL real
PORT = int(os.environ.get("PORT", 10000))

# Dicionário para controlar limite diário
usuarios_limite = {}

# ------------------- HANDLERS -------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá! Bot ativo ✅\nUse /meuid para ver seu ID.\nUse /premium para acessar funções premium."
    )

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"Seu ID é: {user_id}")

async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text("Função Premium ainda em desenvolvimento ⭐")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texto = update.message.text

    # Controle de limite diário
    if user_id not in usuarios_limite:
        usuarios_limite[user_id] = 0
    if usuarios_limite[user_id] >= LIMITE_DIARIO:
        await update.message.reply_text("Você atingiu o limite diário de uso. Tente amanhã.")
        return
    usuarios_limite[user_id] += 1

    # Função de vídeo (exemplo)
    if "vídeo" in texto.lower():
        await update.message.reply_text("Função de vídeo em desenvolvimento 🎬")
        return

    # Função ASAAS (exemplo)
    if "asaas" in texto.lower():
        await update.message.reply_text("Função ASAAS em desenvolvimento 💳")
        return

    # Mensagem padrão
    await update.message.reply_text(f"Você disse: {texto}")

# ------------------- CONFIGURAÇÃO DO BOT -------------------

app = ApplicationBuilder().token(TOKEN).build()

# Adiciona handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("meuid", meuid))
app.add_handler(CommandHandler("premium", premium))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# ------------------- RODA O WEBHOOK -------------------

if __name__ == "__main__":
    print("Bot iniciado... aguardando mensagens")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook_telegram",
        webhook_url=WEBHOOK_URL
    )
