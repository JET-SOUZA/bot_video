# bot.py
# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + yt-dlp
# Atualizado: adiciona premium commands, asaas webhook, health, e correção faststart para mp4 mobile.

import os
import json
import requests
import asyncio
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import unquote
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

import yt_dlp

# aiohttp para endpoints extra (/health, /asaas-webhook)
from aiohttp import web

# ---------------------------------------------------------
# TOKEN (Render)
# ---------------------------------------------------------
TOKEN = (
    os.environ.get("TOKEN") or
    os.environ.get("BOT_TOKEN") or
    os.environ.get("TELEGRAM_TOKEN") or
    os.environ.get("TG_BOT_TOKEN")
)
if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN ou BOT_TOKEN no Render.")

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

# Admin (conforme fornecido)
ADMIN_ID = 5593153639

LIMITE_DIARIO = 10
PORT = int(os.environ.get("PORT", 10000))

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

# Cria cookies.txt a partir da variável de ambiente se existir
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

# ---------------------------------------------------------
# JSON UTILS
# ---------------------------------------------------------
def load_json(path):
    if path.exists():
        with open(path, "r") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ---------------------------------------------------------
# PREMIUM (armazenamento com expiração)
# ---------------------------------------------------------
def _load_premium_raw():
    return load_json(ARQUIVO_PREMIUM)

def _save_premium_raw(data):
    save_json(ARQUIVO_PREMIUM, data)

def load_premium_set():
    """
    Retorna dicionário:
    { "<user_id>": {"ativo": True, "expira": "YYYY-MM-DDTHH:MM:SS"} }
    """
    data = _load_premium_raw()
    if not isinstance(data, dict):
        return {}
    return data

def is_premium(uid):
    data = load_premium_set()
    s = data.get(str(uid))
    if not s:
        return False
    if not s.get("ativo"):
        return False
    exp = s.get("expira")
    if not exp:
        return True
    try:
        exp_dt = datetime.fromisoformat(exp)
        return exp_dt > datetime.utcnow()
    except:
        return True

def add_premium(uid, days=30):
    data = load_premium_set()
    now = datetime.utcnow()
    if str(uid) in data and data[str(uid)].get("expira"):
        # estende
        try:
            current = datetime.fromisoformat(data[str(uid)]["expira"])
            if current > now:
                new_exp = current + timedelta(days=days)
            else:
                new_exp = now + timedelta(days=days)
        except:
            new_exp = now + timedelta(days=days)
    else:
        new_exp = now + timedelta(days=days)
    data[str(uid)] = {"ativo": True, "expira": new_exp.isoformat()}
    _save_premium_raw(data)
    return data[str(uid)]

def del_premium(uid):
    data = load_premium_set()
    if str(uid) in data:
        del data[str(uid)]
        _save_premium_raw(data)
        return True
    return False

def get_premium_info(uid):
    data = load_premium_set()
    return data.get(str(uid))

# garantir admin como premium (opcional)
_p = load_premium_set()
if str(ADMIN_ID) not in _p:
    # admin ganha premium permanente por segurança
    _p[str(ADMIN_ID)] = {"ativo": True, "expira": (datetime.utcnow() + timedelta(days=3650)).isoformat()}
    _save_premium_raw(_p)

# ---------------------------------------------------------
# ASAAS — verificação periódica (fallback) e webhook handler
# ---------------------------------------------------------
def verificar_pagamentos_asaas():
    try:
        if not ASAAS_API_KEY:
            print("Asaas desativado (sem API KEY).")
            return

        url = f"{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()

        for p in data.get("data", []):
            # procura metadata.telegram_id (padrão que já usamos)
            meta = p.get("metadata") or {}
            if isinstance(meta, dict) and "telegram_id" in meta:
                try:
                    uid = int(meta["telegram_id"])
                    # por padrão damos 30 dias (ajustável)
                    add_premium(uid, days=30)
                except:
                    pass
        print("Verificação Asaas executada.")
    except Exception as e:
        print("Erro Asaas:", e)

async def asaas_webhook_handler(request):
    """
    Recebe notificações do Asaas.
    O Asaas envia um JSON com "event" e "payment" (quando aplicável).
    Exemplo (simplificado):
    {
      "event": "PAYMENT_CONFIRMED",
      "data": {
         "id": "...",
         "status": "CONFIRMED",
         "metadata": {"telegram_id": "123456789"}
      }
    }
    """
    try:
        j = await request.json()
    except:
        return web.Response(text="invalid json", status=400)

    # tenta achar metadata
    # formatos do asaas podem variar; procuramos em j["data"] ou j["payment"] etc.
    # eventos comuns: "PAYMENT_CONFIRMED", "PAYMENT_CREATED", etc.
    event = j.get("event") or j.get("notification") or ""
    payload = j.get("data") or j.get("payment") or j.get("object") or {}

    # tenta extrair metadata.telegram_id
    meta = {}
    if isinstance(payload, dict):
        meta = payload.get("metadata") or {}

    # fallback: às vezes payload é string JSON
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except:
            meta = {}

    telegram_id = None
    if isinstance(meta, dict) and "telegram_id" in meta:
        try:
            telegram_id = int(meta["telegram_id"])
        except:
            telegram_id = None

    # Se achou telegram_id e evento confirmado, ativa premium
    if telegram_id:
        # Considera confirmado por padrão se event contém CONFIRMED ou status CONFIRMED
        status = (payload.get("status") or "").upper()
        if "CONFIRMED" in event.upper() or status == "CONFIRMED" or "PAYMENT_CONFIRMED" in event.upper():
            add_premium(telegram_id, days=30)  # 30 dias por pagamento (ajustar conforme necessidade)
            print(f"Asaas: Premium ativado para {telegram_id} via webhook.")
            return web.Response(text="ok", status=200)
        else:
            # pode ser criado; só logamos
            print(f"Asaas webhook recebido (não confirmado): event={event} status={status} telegram_id={telegram_id}")
            return web.Response(text="ignored", status=200)

    # se não houver telegram_id, tentamos inferir no description
    description = payload.get("description") or payload.get("externalReference") or ""
    if description:
        m = re.search(r"\b(\d{6,12})\b", str(description))
        if m:
            try:
                tid = int(m.group(1))
                add_premium(tid, days=30)
                print(f"Asaas: Premium ativado (inferido) para {tid} via webhook.")
                return web.Response(text="ok-inferred", status=200)
            except:
                pass

    # se não achou, ainda retornamos 200 para não fazer retry agressivo
    print("Asaas webhook recebido sem telegram_id.")
    return web.Response(text="no-telegram-id", status=200)

# ---------------------------------------------------------
# LIMITE DIÁRIO
# ---------------------------------------------------------
def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]

def incrementar_download(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        data[str(uid)]["downloads"] += 1
    save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]

# ---------------------------------------------------------
# COMANDOS
# ---------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Jet TikTokShop Bot*\n\nEnvie um link para baixar vídeo.\n⚠️ Free: 10/dia\n💎 Premium: ilimitado",
        parse_mode="Markdown"
    )

async def planos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # mantém botões para pagamento Asaas (exemplo de links)
    kb = [
        [InlineKeyboardButton("💎 1 Mês – R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses – R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano – R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")],
    ]
    await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))

async def duvida_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")

async def meuid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")

# ADMIN: add/del premium
async def addpremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Apenas o admin pode usar este comando.")

    if not context.args:
        return await update.message.reply_text("Uso: /addpremium <user_id> [dias]\nEx: /addpremium 123456789 30")

    try:
        uid = int(context.args[0])
        days = int(context.args[1]) if len(context.args) > 1 else 30
        info = add_premium(uid, days=days)
        await update.message.reply_text(f"✅ Usuário {uid} adicionado como premium por {days} dias.\nValidade: {info['expira']}")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def delpremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Apenas o admin pode usar este comando.")

    if not context.args:
        return await update.message.reply_text("Uso: /delpremium <user_id>")

    try:
        uid = int(context.args[0])
        ok = del_premium(uid)
        if ok:
            await update.message.reply_text(f"✅ Usuário {uid} removido do premium.")
        else:
            await update.message.reply_text(f"⚠️ Usuário {uid} não era premium.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def meupremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    info = get_premium_info(uid)
    if info and info.get("ativo"):
        exp = info.get("expira")
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp)
                await update.message.reply_text(f"✅ Você é premium até {exp_dt.isoformat()} (UTC).")
                return
            except:
                pass
        await update.message.reply_text("✅ Você é premium (sem data de expiração definida).")
    else:
        await update.message.reply_text("❌ Você não é premium. Veja /planos para assinar.")

# ---------------------------------------------------------
# SHOPEE UNIVERSAL PATCH 2025
# (mantive seu código praticamente igual)
# ---------------------------------------------------------
def extrair_video_shopee(url):
    if "br.shp.ee" in url or "shp.ee" in url:
        try:
            r = requests.head(url, allow_redirects=True, timeout=10)
            url = r.url
        except:
            pass

    if "redir=" in url:
        try:
            redir = re.search(r"redir=([^&]+)", url).group(1)
            url = unquote(redir)
        except:
            pass

    m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", url)
    if not m:
        try:
            html = requests.get(url, timeout=10).text
            m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html)
        except:
            pass

    if not m:
        return None

    share_id = m.group(1)
    api_url = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
    try:
        data = requests.get(api_url, timeout=10).json()
    except:
        data = {}

    video_url = (
        data.get("data", {}).get("play") or
        data.get("data", {}).get("video_url") or
        data.get("data", {}).get("url") or
        (data.get("data", {}).get("videos", [{}])[0].get("url") if data.get("data", {}).get("videos") else None) or
        data.get("data", {}).get("path")
    )

    if not video_url:
        try:
            html = requests.get(url, timeout=10).text
            mp4 = re.search(r"https?://[^\s\"']+\.mp4", html)
            if mp4:
                return mp4.group(0)
            m3u8 = re.search(r"https?://[^\s\"']+\.m3u8[^\s\"']*", html)
            if m3u8:
                return m3u8.group(0)
            json_url = re.search(r'"url":"(https:[^"]+)"', html)
            if json_url:
                return json_url.group(1)
            json_play = re.search(r'"play[^"]*":"(https:[^"]+)"', html)
            if json_play:
                return json_play.group(1)
        except:
            pass

    return video_url

# ---------------------------------------------------------
# DOWNLOAD HANDLER (com faststart para mobile)
# ---------------------------------------------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.message.from_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    verificar_pagamentos_asaas()

    if not is_premium(uid):
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    # Patch Shopee
    if "shopee.com" in url or "shp.ee" in url or "sv.shopee.com" in url:
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)
        if not video_url:
            return await update.message.reply_text(
                "❌ Não foi possível extrair vídeo. "
                "(tente enviar o link longo ou o br.shp.ee sem parâmetros)"
            )
        url = video_url

    await update.message.reply_text("⏳ Baixando...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        # ydl opts with faststart to make mp4 mobile-friendly
        ydl_opts = {
            "outtmpl": output,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            # faststart garante que o moov atom fique no começo do arquivo
            "postprocessor_args": ["-movflags", "faststart"],
        }

        # se cookies tiktok setados
        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # prepare_filename dá nome final (após merge)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, lambda: run(url))

        # enviar como video (telegram aceita mp4)
        with open(file_path, "rb") as f:
            await update.message.reply_video(f, caption="✅ Seu vídeo está aqui!")

        # apagar
        try:
            os.remove(file_path)
        except:
            pass

        if not is_premium(uid):
            novo = incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {novo}/{LIMITE_DIARIO}")

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# ---------------------------------------------------------
# AIOHTTP app: health + asaas-webhook + (outros possíveis)
# ---------------------------------------------------------
async def health_handler(request):
    return web.Response(text="ok", status=200)

# ---------------------------------------------------------
# MAIN (WEBHOOK) - cria aiohttp web_app e injeta no PTB run_webhook
# ---------------------------------------------------------
def main():
    # atualiza assinaturas asaas pontualmente (opcional)
    verificar_pagamentos_asaas()

    # cria aplicação Telegram
    application = Application.builder().token(TOKEN).build()

    # registrar comandos
    async def set_commands(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Iniciar bot"),
            BotCommand("planos", "Planos premium"),
            BotCommand("duvida", "Ajuda"),
            BotCommand("meuid", "Mostrar ID"),
            BotCommand("meupremium", "Ver status premium"),
            BotCommand("addpremium", "Adicionar premium (admin)"),
            BotCommand("delpremium", "Remover premium (admin)"),
        ])
    application.post_init = set_commands

    # handlers bot
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("planos", planos_cmd))
    application.add_handler(CommandHandler("duvida", duvida_cmd))
    application.add_handler(CommandHandler("meuid", meuid_cmd))

    application.add_handler(CommandHandler("addpremium", addpremium_cmd))
    application.add_handler(CommandHandler("delpremium", delpremium_cmd))
    application.add_handler(CommandHandler("meupremium", meupremium_cmd))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    # cria web_app aiohttp para health e asaas + Telegram webhook path
    web_app = web.Application()
    web_app.router.add_get("/health", health_handler)
    web_app.router.add_post("/asaas-webhook", asaas_webhook_handler)

    # PTB vai registrar sua rota de webhook no caminho /webhook
    # (usamos url_path="webhook" tal como foi combinado)
    # precisamos montar o handler do PTB dentro do mesmo web_app.
    # Application.run_webhook possui parâmetro `web_app` para usar um web application existente.
    # (Caso sua versão não aceite, remova o web_app e use o default — o endpoint /asaas-webhook
    #  pode então ser exposto por outro servidor.)
    #
    # URL pública:
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("HOSTNAME") or f"localhost:{PORT}"
    webhook_url = f"https://{hostname}/webhook"

    print(f"Iniciando bot (webhook) na porta {PORT}, webhook_url={webhook_url}")

    # rodar run_webhook usando o web_app criado
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=webhook_url,
        web_app=web_app  # injeta nosso aiohttp app (disponível em PTB20+)
    )

if __name__ == "__main__":
    main()
