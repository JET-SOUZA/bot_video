# -----------------------
# Planos Premium - 3 opções (links fixos Asaas)
# -----------------------
async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💎 1 Mês - R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses - R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano - R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    texto = (
        "💎 Escolha seu plano Premium para liberar downloads ilimitados:\n\n"
        "📌 Clique no botão para pagar via PIX ou cartão."
    )
    await update.message.reply_text(texto, reply_markup=markup)

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com", parse_mode="Markdown")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{user_id}`", parse_mode="Markdown")
