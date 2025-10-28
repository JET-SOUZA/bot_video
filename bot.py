# bot.py
# Jet_TikTokShop Bot v4.6 - Planos + Notificações + Lembrete 1 dia antes
# Adaptado para Render (webhook + Flask + background task)

import os
import json
import asyncio
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path

import aiohttp
import yt_dlp
from flask import Flask, request, redirect
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -----------------------
# Configurações (variáveis de ambiente)
# -----------------------
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 5593153639  # seu ID fixo
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # ex: https://meu-app.onrender.com/webhook_telegram

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
def carregar_json(caminho: Path):
    if caminho.exists():
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def salvar_json(caminho: Path, dados):
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

# premium.json estrutura:
# {"premium_users": {"<telegram_id>": "YYYY-MM-DD", ...}}
def carregar_premium():
    dados = carregar_json(ARQUIVO_PREMIUM)
    return dados.get("premium_users", {})


def salvar_premium(dct):
    salvar_json(ARQUIVO_PREMIUM, {"premium_users": dct})

# contador de downloads (downloads.json)
def carregar_contador():
    return carregar_json(ARQUIVO_CONTADOR)


def salvar_contador(dados):
    salvar_json(ARQUIVO_CONTADOR, dados)

# -----------------------
# Telegram / Flask setup
# -----------------------
flask_app = Flask(__name__)
app = None  # ApplicationBuilder result será armazenado aqui

# -----------------------
# Helpers de assinatura
# -----------------------
def usuario_eh_premium(telegram_id: int):
    premium = carregar_premium()
    s = premium.get(str(telegram_id))
    if not s:
        return False
    try:
        exp = datetime.strptime(s, "%Y-%m-%d").date()
        return exp >= date.today()
    except Exception:
        return False


def set_premium_for(telegram_id: int, dias: int):
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
    # envia link para a página /planos já com telegram_id para permitir checkout direto
    telegram_id = update.effective_user.id
    if WEBHOOK_URL:
        base_url = WEBHOOK_URL.replace("/webhook_telegram", "")
    else:
        # fallback - tente montar baseado no host
        base_url = request.url_root.rstrip("/") if request else ""
    link_planos = f"{base_url}/planos?telegram_id={telegram_id}"
    await update.message.reply_text(
        f"💎 Veja os planos Premium disponíveis e escolha o seu:\n\n👉 {link_planos}"
    )


# Mantemos o callback handler como fallback (para quem quiser pagar direto pelo Telegram)
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
# Webhook routes
# -----------------------
@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    data = request.get_json(force=True)
    update = Update.de_json(data, app.bot)
    app.update_queue.put_nowait(update)
    return "OK", 200


@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    data = request.json or {}
    status = data.get("status")
    metadata = data.get("metadata") or {}
    telegram_id = int(metadata.get("telegram_id", 0) or 0)
    plan_key = metadata.get("plan_key")
    if telegram_id and plan_key:
        if status == "CONFIRMED":
            dias = PLANOS.get(plan_key, {}).get("dias", 0)
            venc = set_premium_for(telegram_id, dias)
            asyncio.create_task(_notify_payment_confirmed(telegram_id, plan_key, venc))
        elif status in ("CANCELED", "EXPIRED"):
            remove_premium(telegram_id)
            asyncio.create_task(_notify_payment_canceled(telegram_id, plan_key, status))
    return "OK", 200


# -----------------------
# PÁGINA /planos e /criar_pagamento (integração Asaas)
# -----------------------
@flask_app.route("/planos", methods=["GET"])
def planos_page():
    # Monta página responsiva com destaque no plano recomendado
    telegram_id = request.args.get("telegram_id", "")
    base_url = request.url_root.rstrip("/")

    planos_html = ""
    recommended = "3m"  # destaque para 3 meses por exemplo
    for key, p in PLANOS.items():
        destaque = "recommended" if key == recommended else ""
        planos_html += f"""
        <div class='plano {destaque}'>
            <div class='badge'>{'RECOMENDADO' if destaque else ''}</div>
            <h2>{p['descricao']}</h2>
            <p class='valor'>R$ {p['valor']:.2f}</p>
            <p class='periodo'>{p['dias']} dias</p>
            <a href='{base_url}/criar_pagamento/{key}?telegram_id={telegram_id}' class='botao'>Assinar</a>
        </div>
        """

    html = f"""
    <!doctype html>
    <html lang='pt-BR'>
    <head>
      <meta charset='utf-8'>
      <meta name='viewport' content='width=device-width,initial-scale=1'>
      <title>Planos Premium - Jet TikTokShop</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; background: #0b1020; color: #e6eef8; margin:0; padding:20px }}
        .container {{ max-width:980px; margin:0 auto; text-align:center }}
        h1 {{ color:#7cf2b3; margin-bottom:6px }}
        p.lead {{ color:#a9cbd6 }}
        .planos {{ display:flex; gap:18px; justify-content:center; flex-wrap:wrap; margin-top:24px }}
        .plano {{ background:linear-gradient(180deg,#0f1724,#111827); border-radius:14px; padding:20px; width:260px; box-shadow:0 8px 30px rgba(0,0,0,0.6); border:1px solid rgba(124,242,179,0.08); position:relative }}
        .plano.recommended {{ transform:scale(1.03); border-color: rgba(124,242,179,0.28); box-shadow:0 12px 40px rgba(0,0,0,0.7) }}
        .plano h2 {{ margin:6px 0 4px 0; color:#bff7d9 }}
        .valor {{ font-size:22px; font-weight:700; margin:8px 0 }}
        .periodo {{ color:#9fb7c7; margin-bottom:12px }}
        .botao {{ display:inline-block; padding:10px 18px; background:#7cf2b3; color:#042016; border-radius:10px; text-decoration:none; font-weight:700 }}
        .badge {{ position:absolute; top:10px; right:10px; background:#ffcf5c; color:#2a1b00; padding:6px 8px; border-radius:8px; font-weight:700; font-size:12px }}
        footer {{ margin-top:28px; color:#93b6c0; font-size:14px }}
      </style>
    </head>
    <body>
      <div class='container'>
        <h1>Planos Premium</h1>
        <p class='lead'>Escolha o plano que mais combina com você. Pagamento via PIX (Asaas).</p>
        <div class='planos'>
          {planos_html}
        </div>
        <footer>Ao pagar, confirme que usou o mesmo Telegram ID mostrado no link.</footer>
      </div>
    </body>
    </html>
    """
    return html


@flask_app.route("/criar_pagamento/<plan_key>", methods=["GET"])
def criar_pagamento(plan_key):
    telegram_id = request.args.get("telegram_id", "")
    if not telegram_id.isdigit():
        return "Erro: ID do Telegram inválido.", 400

    async def _create():
        async with aiohttp.ClientSession() as session:
            return await criar_cobranca_asaas(session, int(telegram_id), plan_key)

    try:
        # roda a coroutine em um novo loop (Flask roda em thread separada do loop principal do bot)
        result = asyncio.run(_create())
        link = result.get("link")
        if link:
            # redireciona automaticamente para o checkout (PIX / payment link)
            return redirect(link)
        else:
            raw = result.get("raw")
            return f"<h2>Erro ao gerar pagamento.</h2><pre>{json.dumps(raw, ensure_ascii=False, indent=2)}</pre>", 500
    except Exception as e:
        return f"<h2>Erro ao criar pagamento: {e}</h2>", 500


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
# Background: verifica expirações e avisa 1 dia antes
# -----------------------
async def expirations_watcher():
    await asyncio.sleep(5)  # espera app subir
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
                if dias_restantes == 1:
                    try:
                        await app.bot.send_message(chat_id=uid,
                                                   text="⏳ Seu plano Premium expira amanhã. Renove para não perder os benefícios.")
                        await app.bot.send_message(chat_id=ADMIN_ID,
                                                   text=f"⚠️ Aviso: plano do usuário {uid} expira amanhã ({venc_s}).")
                    except Exception as e:
                        print("Erro notify 1 dia:", e)
                if dias_restantes < 0:
                    remove_premium(uid)
                    try:
                        await app.bot.send_message(chat_id=uid,
                                                   text="❌ Seu plano Premium expirou. Para renovar, use /planos.")
                        await app.bot.send_message(chat_id=ADMIN_ID,
                                                   text=f"❌ Plano do usuário {uid} expirou em {venc_s}.")
                    except Exception as e:
                        print("Erro notify expired:", e)
        except Exception as e:
            print("Erro no watcher:", e, traceback.format_exc())
        await asyncio.sleep(24 * 60 * 60)

# -----------------------
# Inicialização assíncrona do bot
# -----------------------
async def start_app():
    global app
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN não configurado.")
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("planos", planos_handler))
    app.add_handler(CommandHandler("duvida", duvida_handler))
    app.add_handler(CommandHandler("meuid", meuid_handler))
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CallbackQueryHandler(planos_callback, pattern=r"^plan:"))
    app.add_handler(CommandHandler("premiumlist", premiumlist_handler))
    app.add_handler(CommandHandler("forceadd", forceadd_handler))
    app.add_handler(CommandHandler("forcedel", forcedel_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video_handler))

    async def post_init(a):
        await a.bot.set_my_commands([
            BotCommand("start", "Iniciar"),
            BotCommand("planos", "Ver planos Premium"),
            BotCommand("duvida", "Ajuda e contato"),
            BotCommand("meuid", "Ver seu ID")
        ])
    app.post_init = post_init

    await app.initialize()
    if WEBHOOK_URL:
        try:
            await app.bot.set_webhook(WEBHOOK_URL)
            print("✅ Webhook configurado:", WEBHOOK_URL)
        except Exception as e:
            print("Falha ao setar webhook:", e)
    await app.start()
    print("🤖 Bot initialized and started (webhook mode).")
    asyncio.create_task(expirations_watcher())

# -----------------------
# Flask thread
# -----------------------
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    @flask_app.route("/", methods=["GET"])
    def index():
        return "🤖 Bot ativo!", 200
    flask_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    flask_thread = asyncio.get_event_loop().run_in_executor(None, run_flask)
    try:
        asyncio.run(start_app())
    except KeyboardInterrupt:
        print("Exiting...")
