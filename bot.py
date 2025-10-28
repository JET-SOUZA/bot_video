import os
import json
import asyncio
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any

import aiohttp
import yt_dlp
from flask import Flask, request, redirect
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# ==========================
# CONFIGURAÇÕES
# ==========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # ex: https://bot-video-mgli.onrender.com/webhook_telegram
ADMIN_ID = 5593153639
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

# Caminhos
SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"
ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    COOKIES_TIKTOK.write_text(os.environ["COOKIES_TIKTOK"])

# Limites
LIMITE_DIARIO = 10
MAX_VIDEO_MB_SEND = 50

# Planos Premium
PLANOS = {
    "1m": {"valor": 9.90, "descricao": "1 mês", "dias": 30},
    "3m": {"valor": 25.00, "descricao": "3 meses", "dias": 90},
    "1a": {"valor": 89.90, "descricao": "1 ano", "dias": 365},
}

# Flask app
flask_app = Flask(__name__)

# ==========================
# FUNÇÕES DE SUPORTE
# ==========================
def carregar_json(caminho: Path) -> Dict[str, Any]:
    if caminho.exists():
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def salvar_json(caminho: Path, dados: Dict[str, Any]):
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

def carregar_premium() -> Dict[str, str]:
    dados = carregar_json(ARQUIVO_PREMIUM)
    return dados.get("premium_users", {})

def salvar_premium(dct: Dict[str, str]):
    salvar_json(ARQUIVO_PREMIUM, {"premium_users": dct})

def carregar_contador() -> Dict[str, Any]:
    return carregar_json(ARQUIVO_CONTADOR)

def salvar_contador(dados: Dict[str, Any]):
    salvar_json(ARQUIVO_CONTADOR, dados)

def usuario_eh_premium(telegram_id: int) -> bool:
    premium = carregar_premium()
    s = premium.get(str(telegram_id))
    if not s:
        return False
    try:
        exp = datetime.strptime(s, "%Y-%m-%d").date()
        return exp >= date.today()
    except Exception:
        return False

def set_premium_for(telegram_id: int, dias: int) -> str:
    premium = carregar_premium()
    hoje = date.today()
    key = str(telegram_id)
    if key in premium:
        try:
            atual = datetime.strptime(premium[key], "%Y-%m-%d").date()
            inicio = max(atual, hoje)
        except Exception:
            inicio = hoje
    else:
        inicio = hoje
    novo_venc = inicio + timedelta(days=dias)
    premium[key] = novo_venc.strftime("%Y-%m-%d")
    salvar_premium(premium)
    return premium[key]

def remove_premium(telegram_id: int):
    premium = carregar_premium()
    key = str(telegram_id)
    if key in premium:
        del premium[key]
        salvar_premium(premium)

# ==========================
# HANDLERS TELEGRAM
# ==========================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎬 *Bem-vindo ao Jet_TikTokShop!*\n\n"
        "Envie o link do vídeo para baixar.\n\n"
        "Use /planos para assinar o Premium 💎"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def planos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    base_url = WEBHOOK_URL.replace("/webhook_telegram", "") if WEBHOOK_URL else "https://seuapp.example.com"
    link_planos = f"{base_url}/planos?telegram_id={telegram_id}"
    await update.message.reply_text(f"💎 Veja os planos Premium:\n{link_planos}")

async def duvida_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com")

async def meuid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu Telegram ID: `{update.effective_user.id}`", parse_mode="Markdown")

# ==========================
# DOWNLOAD DE VÍDEOS
# ==========================
async def baixar_video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.message.from_user.id
    if not texto.startswith("http"):
        await update.message.reply_text("❌ Envie um link válido.")
        return

    dados = carregar_contador()
    hoje = str(date.today())
    if str(user_id) not in dados or dados[str(user_id)].get("data") != hoje:
        dados[str(user_id)] = {"data": hoje, "downloads": 0}

    if not usuario_eh_premium(user_id) and dados[str(user_id)]["downloads"] >= LIMITE_DIARIO:
        await update.message.reply_text("⚠️ Limite diário atingido. Assine o Premium.")
        return

    status_msg = await update.message.reply_text("⏳ Preparando download...")
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        out_template = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")
        ydl_opts = {
            "outtmpl": out_template,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "ignoreerrors": True,
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
        tamanho_mb = Path(candidato).stat().st_size / (1024 * 1024)
        with open(candidato, "rb") as f:
            if tamanho_mb > MAX_VIDEO_MB_SEND:
                await update.message.reply_document(f, caption="✅ Aqui está seu vídeo (documento).")
            else:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo em alta qualidade!")

        if not usuario_eh_premium(user_id):
            dados[str(user_id)]["downloads"] += 1
            salvar_contador(dados)
            await update.message.reply_text(
                f"📊 Uso diário: *{dados[str(user_id)]['downloads']}/{LIMITE_DIARIO}*", parse_mode="Markdown"
            )

        Path(candidato).unlink(missing_ok=True)
        await status_msg.delete()
    except Exception as e:
        print(traceback.format_exc())
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# ==========================
# ASAAS WEBHOOK
# ==========================
@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    data = request.get_json(force=True) or {}
    status = data.get("status")
    metadata = data.get("metadata") or {}
    telegram_id = int(metadata.get("telegram_id", 0) or 0)
    plan_key = metadata.get("plan_key")
    if telegram_id and plan_key:
        if status == "CONFIRMED":
            dias = PLANOS.get(plan_key, {}).get("dias", 0)
            venc = set_premium_for(telegram_id, dias)
            asyncio.run_coroutine_threadsafe(
                app.bot.send_message(telegram_id, f"✅ Pagamento confirmado! Plano ativo até {venc}."),
                ASYNC_LOOP,
            )
            asyncio.run_coroutine_threadsafe(
                app.bot.send_message(ADMIN_ID, f"💰 Novo Premium: {telegram_id} ({PLANOS[plan_key]['descricao']}) até {venc}"),
                ASYNC_LOOP,
            )
        elif status in ("CANCELED", "EXPIRED"):
            remove_premium(telegram_id)
            asyncio.run_coroutine_threadsafe(
                app.bot.send_message(telegram_id, f"⚠️ Seu pagamento foi marcado como {status}."),
                ASYNC_LOOP,
            )
    return "OK", 200

# ==========================
# FLASK ROTAS
# ==========================
@flask_app.route("/", methods=["GET"])
def index():
    return "🤖 Bot ativo!", 200

@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    data = request.get_json(force=True)
    update = Update.de_json(data, app.bot)
    app.update_queue.put_nowait(update)
    return "OK", 200

# ==========================
# WATCHER DE EXPIRAÇÕES
# ==========================
async def expirations_watcher():
    await asyncio.sleep(5)
    while True:
        try:
            premium = carregar_premium()
            hoje = date.today()
            for uid_str, venc_s in list(premium.items()):
                try:
                    uid = int(uid_str)
                    venc = datetime.strptime(venc_s, "%Y-%m-%d").date()
                except Exception:
                    continue
                dias_restantes = (venc - hoje).days
                if dias_restantes == 3:
                    msg = "⏳ Seu plano Premium vence em 3 dias!"
                elif dias_restantes == 1:
                    msg = "🚨 Seu plano Premium vence amanhã!"
                elif dias_restantes == 0:
                    msg = "⚠️ Seu plano Premium vence hoje!"
                elif dias_restantes < 0:
                    remove_premium(uid)
                    msg = "❌ Seu plano Premium expirou. Renove com /planos!"
                else:
                    continue
                try:
                    await app.bot.send_message(chat_id=uid, text=msg)
                    await app.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 Aviso enviado a {uid}: {msg}")
                except Exception:
                    pass
        except Exception as e:
            print("Erro no watcher:", e)
        await asyncio.sleep(24 * 60 * 60)

# ==========================
# MAIN: START APP + FLASK
# ==========================
app = None
ASYNC_LOOP = None

async def start_app():
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("planos", planos_handler))
    app.add_handler(CommandHandler("duvida", duvida_handler))
    app.add_handler(CommandHandler("meuid", meuid_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video_handler))

    async def _post_init(a):
        await a.bot.set_my_commands([
            BotCommand("start", "Iniciar"),
            BotCommand("planos", "Ver planos Premium"),
            BotCommand("duvida", "Ajuda e contato"),
            BotCommand("meuid", "Ver seu ID"),
        ])
    app.post_init = _post_init

    await app.initialize()
    await app.start()
    await app.bot.set_webhook(WEBHOOK_URL)
    print("✅ Webhook ativo em:", WEBHOOK_URL)
    asyncio.create_task(expirations_watcher())

async def main():
    global ASYNC_LOOP
    ASYNC_LOOP = asyncio.get_running_loop()
    await start_app()
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    import threading
    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=port), daemon=True).start()
    asyncio.run(main())
