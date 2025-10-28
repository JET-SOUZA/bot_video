# bot.py
# Jet_TikTokShop Bot - Webhook + Flask + Asaas + Expiration watcher
# Versão: unificada e compatível com Render

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

# -----------------------
# Configurações (variáveis de ambiente)
# -----------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # token do bot
ADMIN_ID = 5593153639  # seu telegram id
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # ex: https://bot-video-mgli.onrender.com/webhook_telegram

# paths
SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"
ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

# cria arquivo cookies a partir da env var se fornecida
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    COOKIES_TIKTOK.write_text(os.environ["COOKIES_TIKTOK"])

# Chrome bin se necessário para yt-dlp
CHROME_BIN = os.environ.get("CHROME_BIN")

# Limites
LIMITE_DIARIO = 10
MAX_VIDEO_MB_SEND = 50

# Planos Premium
PLANOS = {
    "1m": {"valor": 9.90, "descricao": "1 mês", "dias": 30},
    "3m": {"valor": 25.00, "descricao": "3 meses", "dias": 90},
    "1a": {"valor": 89.90, "descricao": "1 ano", "dias": 365},
}

# -----------------------
# Utilitários JSON
# -----------------------
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

# -----------------------
# Helpers de assinatura
# -----------------------
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

# -----------------------
# ASYNC Asaas (criar pagamento)
# -----------------------
async def criar_cobranca_asaas(session: aiohttp.ClientSession, telegram_id: int, plan_key: str):
    plano = PLANOS.get(plan_key)
    if not plano:
        raise ValueError("Plano inválido")
    payload = {
        "customer": "CUS_ID_DO_CLIENTE",  # opcional: trocar se você tiver cliente cadastrado no Asaas
        "billingType": "PIX",
        "value": round(plano["valor"], 2),
        "dueDate": date.today().strftime("%Y-%m-%d"),
        "description": f"Assinatura {plano['descricao']} - Jet_TikTokShop",
        "metadata": {"telegram_id": str(telegram_id), "plan_key": plan_key}
    }
    headers = {"access_token": ASAAS_API_KEY, "Content-Type": "application/json"}
    async with session.post(f"{ASAAS_BASE_URL}/payments", json=payload, headers=headers) as resp:
        data = await resp.json()
        # tenta campos comuns que o Asaas pode retornar
        link = data.get("pixQrCode") or data.get("paymentLink") or data.get("invoiceUrl") or None
        return {"raw": data, "link": link}

# -----------------------
# Handlers do bot
# -----------------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎬 *Bem-vindo ao Jet_TikTokShop!*\n\n"
        "Envie o link do vídeo para baixar.\n\n"
        "Use /planos para assinar o Premium (1m, 3m, 1a)."
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def planos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    # envia um link para a página /planos com telegram_id (para checkout rápido)
    if WEBHOOK_URL:
        base_url = WEBHOOK_URL.replace("/webhook_telegram", "")
    else:
        base_url = "https://seuapp.example.com"
    link_planos = f"{base_url}/planos?telegram_id={telegram_id}"
    await update.message.reply_text(f"💎 Veja os planos Premium e escolha o seu:\n{link_planos}")

async def planos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, plan_key = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_text("Plano inválido.")
        return
    telegram_id = query.from_user.id
    async with aiohttp.ClientSession() as session:
        try:
            result = await criar_cobranca_asaas(session, telegram_id, plan_key)
            link = result.get("link") or "https://www.asaas.com"
            texto = f"🔗 Pagamento criado. Clique para pagar ({PLANOS[plan_key]['descricao']}):"
            keyboard = [[InlineKeyboardButton("💰 Pagar agora", url=link)]]
            await query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await query.edit_message_text(f"Erro ao criar pagamento: {e}")

async def duvida_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com")

async def meuid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{update.effective_user.id}`", parse_mode="Markdown")

# -----------------------
# Download handler + contador diário
# -----------------------
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
        # resolve short links
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
            "no_warnings": True,
        }
        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
        if CHROME_BIN:
            ydl_opts["browser_executable"] = CHROME_BIN

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

        if not candidato or not Path(candidato).exists():
            await update.message.reply_text("⚠️ Não foi possível localizar o arquivo baixado.")
            return

        tamanho_mb = Path(candidato).stat().st_size / (1024 * 1024)
        with open(candidato, "rb") as f:
            if tamanho_mb > MAX_VIDEO_MB_SEND:
                await update.message.reply_document(f, caption="✅ Aqui está seu vídeo (documento).")
            else:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo em alta qualidade!")

        # atualiza contador
        if not usuario_eh_premium(user_id):
            dados[str(user_id)]["downloads"] += 1
            salvar_contador(dados)
            await update.message.reply_text(
                f"📊 Uso diário: *{dados[str(user_id)]['downloads']}/{LIMITE_DIARIO}*", parse_mode="Markdown"
            )
        Path(candidato).unlink(missing_ok=True)
        await status_msg.delete()
    except Exception as e:
        tb = traceback.format_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")
        print(tb)
        try:
            await status_msg.delete()
        except Exception:
            pass

# -----------------------
# Admin handlers
# -----------------------
async def premiumlist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    premium = carregar_premium()
    if not premium:
        await update.message.reply_text("Nenhum usuário premium.")
        return
    lines = [f"{uid} — expira em {exp}" for uid, exp in premium.items()]
    await update.message.reply_text("💎 Usuários Premium:\n" + "\n".join(lines))

async def forceadd_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Use: /forceadd <telegram_id> <dias>")
        return
    try:
        tid = int(context.args[0])
        dias = int(context.args[1])
        venc = set_premium_for(tid, dias)
        await update.message.reply_text(f"✅ Adicionado {tid} até {venc}")
    except Exception as e:
        await update.message.reply_text(f"Erro: {e}")

async def forcedel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Use: /forcedel <telegram_id>")
        return
    try:
        tid = int(context.args[0])
        remove_premium(tid)
        await update.message.reply_text(f"✅ Removido {tid} do premium")
    except Exception as e:
        await update.message.reply_text(f"Erro: {e}")

# -----------------------
# Webhook routes (Flask)
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def index():
    return "🤖 Bot ativo!", 200

@flask_app.route("/planos", methods=["GET"])
def planos_page():
    telegram_id = request.args.get("telegram_id", "")
    base_url = request.url_root.rstrip("/")
    planos_html = ""
    recommended = "3m"
    for key, p in PLANOS.items():
        destaque = "RECOMENDADO" if key == recommended else ""
        planos_html += f"""
        <div class='plano'>
            <div class='badge'>{destaque}</div>
            <h2>{p['descricao']}</h2>
            <p class='valor'>R$ {p['valor']:.2f}</p>
            <p class='periodo'>{p['dias']} dias</p>
            <a href='{base_url}/criar_pagamento/{key}?telegram_id={telegram_id}' class='botao'>Assinar</a>
        </div>
        """
    html = f"""
    <html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Planos Premium</title>
    <style>
      body{{font-family:Arial;background:#071427;color:#e6f2f1;padding:20px}}
      .planos{{display:flex;gap:16px;flex-wrap:wrap;justify-content:center}}
      .plano{{background:#0f1724;padding:18px;border-radius:12px;width:220px;box-shadow:0 6px 18px rgba(0,0,0,0.6);text-align:center}}
      .badge{{background:#ffd166;color:#3a2b00;padding:6px;border-radius:8px;font-weight:700;margin-bottom:8px}}
      .valor{{font-size:20px;font-weight:700;margin:6px 0}}
      .botao{{display:inline-block;padding:10px 14px;background:#7cf2b3;color:#042016;border-radius:10px;text-decoration:none;font-weight:700}}
    </style>
    </head><body>
    <h1>Planos Premium</h1><p>Pagamento via PIX (Asaas).</p>
    <div class='planos'>{planos_html}</div>
    <p style='text-align:center;margin-top:18px;color:#97b2b8'>Use o mesmo Telegram ID mostrado no link para que a assinatura seja corretamente associada.</p>
    </body></html>
    """
    return html

@flask_app.route("/criar_pagamento/<plan_key>", methods=["GET"])
def criar_pagamento_route(plan_key):
    telegram_id = request.args.get("telegram_id", "")
    if not telegram_id.isdigit():
        return "Erro: telegram_id inválido.", 400

    # agenda a coroutine no loop principal e aguarda o resultado
    coro = _criar_pagamento_threadsafe(int(telegram_id), plan_key)
    fut = asyncio.run_coroutine_threadsafe(coro, ASYNC_LOOP)
    try:
        result = fut.result(timeout=20)
    except Exception as e:
        return f"<h2>Erro ao gerar pagamento: {e}</h2>", 500

    link = result.get("link")
    if link:
        return redirect(link)
    else:
        raw = result.get("raw")
        return f"<h2>Erro ao gerar pagamento.</h2><pre>{json.dumps(raw, ensure_ascii=False, indent=2)}</pre>", 500

async def _criar_pagamento_threadsafe(telegram_id: int, plan_key: str):
    async with aiohttp.ClientSession() as session:
        return await criar_cobranca_asaas(session, telegram_id, plan_key)

@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    data = request.get_json(force=True)
    update = Update.de_json(data, app.bot)
    # coloca o update na fila do Application
    app.update_queue.put_nowait(update)
    return "OK", 200

@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    # Asaas envia informações de pagamento/cancelamento
    data = request.get_json(force=True) or {}
    status = data.get("status")
    metadata = data.get("metadata") or {}
    telegram_id = int(metadata.get("telegram_id", 0) or 0)
    plan_key = metadata.get("plan_key")
    if telegram_id and plan_key:
        if status == "CONFIRMED":
            dias = PLANOS.get(plan_key, {}).get("dias", 0)
            venc = set_premium_for(telegram_id, dias)
            asyncio.run_coroutine_threadsafe(_notify_payment_confirmed(telegram_id, plan_key, venc), ASYNC_LOOP)
        elif status in ("CANCELED", "EXPIRED"):
            remove_premium(telegram_id)
            asyncio.run_coroutine_threadsafe(_notify_payment_canceled(telegram_id, plan_key, status), ASYNC_LOOP)
    return "OK", 200

# -----------------------
# Notificações assíncronas
# -----------------------
async def _notify_payment_confirmed(telegram_id: int, plan_key: str, venc_str: str):
    try:
        await app.bot.send_message(chat_id=telegram_id,
                                   text=f"✅ Pagamento confirmado! Seu plano {PLANOS[plan_key]['descricao']} foi ativado até {venc_str}.")
        await app.bot.send_message(chat_id=ADMIN_ID,
                                   text=f"✅ Usuário {telegram_id} ativou/renovou {PLANOS[plan_key]['descricao']} até {venc_str}.")
    except Exception as e:
        print("Erro notify_confirmed:", e)

async def _notify_payment_canceled(telegram_id: int, plan_key: str, status: str):
    try:
        await app.bot.send_message(chat_id=telegram_id,
                                   text=f"⚠️ Seu pagamento ({PLANOS.get(plan_key, {}).get('descricao','')}) foi marcado como {status}.")
        await app.bot.send_message(chat_id=ADMIN_ID,
                                   text=f"⚠️ Pagamento do usuário {telegram_id} para {plan_key} foi marcado como {status}.")
    except Exception as e:
        print("Erro notify_canceled:", e)

# -----------------------
# Background: verifica expirações e avisa 3d/1d/0d e expira no dia seguinte
# -----------------------
async def expirations_watcher():
    # roda logo após o bot iniciar
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
                # 3 dias antes
                if dias_restantes == 3:
                    msg = "⏳ Oi! Seu plano Premium vence em 3 dias 😉 Renove pra continuar aproveitando sem parar!"
                    await _send_user_and_admin(uid, msg)
                # 1 dia antes
                if dias_restantes == 1:
                    msg = "🚨 Seu plano Premium vence amanhã 😬 Renove pra não ficar sem baixar seus vídeos!"
                    await _send_user_and_admin(uid, msg)
                # no dia do vencimento (usuário ainda tem acesso)
                if dias_restantes == 0:
                    msg = "⚠️ Seu plano Premium vence hoje! Aproveite pra renovar antes de perder o acesso ❤️"
                    await _send_user_and_admin(uid, msg)
                # expirado (venc < hoje) -> remove e notifica (isso ocorre no dia seguinte)
                if dias_restantes < 0:
                    remove_premium(uid)
                    try:
                        await app.bot.send_message(chat_id=uid,
                                                   text="❌ Seu plano Premium expirou 😢 — renove com /planos pra voltar a aproveitar tudo!")
                        await app.bot.send_message(chat_id=ADMIN_ID,
                                                   text=f"❌ Plano do usuário {uid} expirou em {venc_s}.")
                    except Exception as e:
                        print("Erro notify expired:", e)
        except Exception as e:
            print("Erro no watcher:", e, traceback.format_exc())
        # espera 24h antes da próxima checagem
        await asyncio.sleep(24 * 60 * 60)

async def _send_user_and_admin(uid: int, msg: str):
    try:
        await app.bot.send_message(chat_id=uid, text=msg)
        await app.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 Aviso para {uid}: {msg}")
    except Exception as e:
        print("Erro send_user_and_admin:", e)

# -----------------------
# Inicialização assíncrona do bot
# -----------------------
app = None   # Application (telegram) - será setado em start_app()
ASYNC_LOOP = None  # loop assíncrono principal (definido em main)

async def start_app():
    global app
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN não configurado.")
    # cria application e handlers
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # adiciona handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("planos", planos_handler))
    app.add_handler(CommandHandler("duvida", duvida_handler))
    app.add_handler(CommandHandler("meuid", meuid_handler))
    app.add_handler(CallbackQueryHandler(planos_callback, pattern=r"^plan:"))
    app.add_handler(CommandHandler("premiumlist", premiumlist_handler))
    app.add_handler(CommandHandler("forceadd", forceadd_handler))
    app.add_handler(CommandHandler("forcedel", forcedel_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video_handler))

    # set commands in Telegram UI
    async def _post_init(a):
        await a.bot.set_my_commands([
            BotCommand("start", "Iniciar"),
            BotCommand("planos", "Ver planos Premium"),
            BotCommand("duvida", "Ajuda e contato"),
            BotCommand("meuid", "Ver seu ID")
        ])
    app.post_init = _post_init

    # inicializa e starta (sem polling)
    await app.initialize()
    await app.start()

    # configura webhook (Telegram enviará updates para /webhook_telegram)
    if WEBHOOK_URL:
        try:
            await app.bot.set_webhook(WEBHOOK_URL)
            print("✅ Webhook configurado:", WEBHOOK_URL)
        except Exception as e:
            print("Falha ao setar webhook:", e)

    # inicia watcher de expirações
    asyncio.create_task(expirations_watcher())

    print("🤖 Bot iniciado (webhook mode).")

# -----------------------
# Função main: roda loop async e Flask em thread
# -----------------------
def run_flask(port: int):
    # Flask roda em thread separada (daemon); o loop async fica na thread principal
    flask_app.run(host="0.0.0.0", port=port)

async def main():
    global ASYNC_LOOP
    ASYNC_LOOP = asyncio.get_running_loop()
    await start_app()
    # mantém o loop vivo para tasks de background (expirations_watcher)
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    # PORT para Render
    PORT = int(os.environ.get("PORT", 10000))

    # start Flask em thread daemon
    flask_thread = asyncio.get_event_loop().run_in_executor(None, run_flask, PORT)

    # roda o loop principal e inicializa o bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Encerrando...")

