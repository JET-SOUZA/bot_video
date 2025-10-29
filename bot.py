# Jet_TikTokShop Bot v4.7 (FINAL)
# Premium via Asaas + QR Code PIX + Vencimento Automático + Webhook Render

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask, request
from datetime import datetime, timedelta
import asyncio, os, json, aiohttp, requests
from io import BytesIO
import threading

# -----------------------
# CONFIGURAÇÕES
# -----------------------
ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "SUA_CHAVE_API_ASAAS_AQUI")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Ex: https://bot-video-mgli.onrender.com
ASAAS_API_URL = "https://www.asaas.com/api/v3"

USUARIOS_PREMIUM = {}

# loop principal — será definido na inicialização
MAIN_LOOP = None

# -----------------------
# CARREGAR / SALVAR USUÁRIOS PREMIUM
# -----------------------
def salvar_premium():
    with open("usuarios_premium.json", "w") as f:
        json.dump(USUARIOS_PREMIUM, f)

def carregar_premium():
    global USUARIOS_PREMIUM
    if os.path.exists("usuarios_premium.json"):
        with open("usuarios_premium.json", "r") as f:
            USUARIOS_PREMIUM = json.load(f)
    else:
        USUARIOS_PREMIUM = {}

carregar_premium()

# -----------------------
# BOT TELEGRAM
# -----------------------
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botoes = [
        [InlineKeyboardButton("💎 1 Mês - R$ 9,90", callback_data="plano_1m")],
        [InlineKeyboardButton("💎 3 Meses - R$ 25,90", callback_data="plano_3m")],
        [InlineKeyboardButton("💎 1 Ano - R$ 89,90", callback_data="plano_1a")],
    ]
    markup = InlineKeyboardMarkup(botoes)
    if update.message:
        await update.message.reply_text(
            "💎 Escolha seu plano Premium para liberar downloads ilimitados:",
            reply_markup=markup,
        )

async def callback_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
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
            try:
                venc = datetime.strptime(info["vencimento"], "%Y-%m-%d").date()
            except Exception:
                continue
            dias_restantes = (venc - hoje).days
            try:
                if dias_restantes == 1:
                    await app.bot.send_message(chat_id=int(user_id), text="⚠️ Seu plano Premium vence amanhã! Renove.")
                elif dias_restantes <= 0:
                    await app.bot.send_message(chat_id=int(user_id), text="❌ Seu plano Premium venceu. Renove para continuar usando.")
            except Exception:
                # ignore send failures (ex: usuário bloqueou bot)
                pass
        await asyncio.sleep(86400)

# -----------------------
# FLASK WEBHOOKS
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/health")
def health():
    return "OK", 200

@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    """
    Recebe a update do Telegram e agenda sua execução no MAIN_LOOP usando
    run_coroutine_threadsafe — função segura entre threads.
    """
    try:
        from telegram import Update
        payload = request.get_json(force=True)
        update = Update.de_json(payload, app.bot)
        if MAIN_LOOP is None:
            # se por algum motivo o MAIN_LOOP não foi inicializado, retorna 500
            return "No main loop", 500
        # agenda a coroutine no loop principal (thread-safe)
        future = asyncio.run_coroutine_threadsafe(app.process_update(update), MAIN_LOOP)
        # opcional: aguardar resultado rapidamente (timeout pequeno) ou não aguardar
        # aqui não aguardamos para não bloquear o request
        return "OK", 200
    except Exception as e:
        # log básico para ajudar no debug (Render logs)
        print("Erro no webhook_telegram:", e)
        return "ERR", 500

@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    try:
        data = request.json
        status = data.get("status")
        telegram_id = int(data.get("metadata", {}).get("telegram_id", 0))
        if telegram_id == 0:
            return "No telegram ID", 400

        planos = {"1 Mês": 30, "3 Meses": 90, "1 Ano": 365}

        if status == "CONFIRMED":
            descricao = data.get("description", "1 Mês")
            dias = planos.get(descricao, 30)
            vencimento = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
            USUARIOS_PREMIUM[str(telegram_id)] = {"vencimento": vencimento, "plano": descricao}
            salvar_premium()
        elif status in ["CANCELED", "EXPIRED"]:
            if str(telegram_id) in USUARIOS_PREMIUM:
                del USUARIOS_PREMIUM[str(telegram_id)]
                salvar_premium()
        return "OK", 200
    except Exception as e:
        print("Erro webhook_asaas:", e)
        return "ERR", 500

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    # use_reloader=False evita criar múltiplos processos/threads no dev server
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# -----------------------
# REGISTRAR WEBHOOK AUTOMATICAMENTE
# -----------------------
async def set_webhook():
    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL não configurada!")
        return
    try:
        # Apaga o webhook antigo (evita conflito com getUpdates)
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook")
        # Registra o webhook correto (assegure que WEBHOOK_URL não termina com /webhook_telegram)
        target = WEBHOOK_URL if WEBHOOK_URL.endswith("/webhook_telegram") else f"{WEBHOOK_URL}/webhook_telegram"
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
        r = requests.post(url, data={"url": target})
        print("🔗 Webhook configurado:", r.json())
    except Exception as e:
        print("Erro ao setar webhook:", e)

# -----------------------
# EXECUÇÃO
# -----------------------
if __name__ == "__main__":
    print("🚀 Iniciando bot Jet_TikTokShop...")

    # 1) inicia Flask em thread (para receber webhooks)
    threading.Thread(target=run_flask, daemon=True).start()

    # 2) pega loop principal e guarda em MAIN_LOOP para usar em run_coroutine_threadsafe
    MAIN_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(MAIN_LOOP)

    # 3) registra webhook (executa no MAIN_LOOP)
    MAIN_LOOP.run_until_complete(set_webhook())

    # 4) inicia task de verificação de vencimentos no MAIN_LOOP
    MAIN_LOOP.create_task(verificar_vencimentos())

    print("✅ Bot pronto e aguardando mensagens do Telegram via Webhook!")
    try:
        MAIN_LOOP.run_forever()
    finally:
        MAIN_LOOP.close()
