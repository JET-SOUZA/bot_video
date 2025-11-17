# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + Instagram Reels + YouTube + yt-dlp
# Atualização 2025-11: addpremium/delpremium + menu admin + mobile fix + contador diário corrigido
# Revisado: cookies IG B64, keepalive Render, fix event loop, /verpremium

import os
import json
import requests
import asyncio
import traceback
import base64
from datetime import datetime, date
from pathlib import Path
from urllib.parse import unquote
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import yt_dlp
import nest_asyncio

# ---------------------------------------------------------
# TOKEN (Render) - mantém compatibilidade com suas variáveis
# ---------------------------------------------------------
TOKEN = (
    os.environ.get("TOKEN")
    or os.environ.get("BOT_TOKEN")
    or os.environ.get("TELEGRAM_TOKEN")
    or os.environ.get("TG_BOT_TOKEN")
)
if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN ou BOT_TOKEN no Render.")

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5593153639"))
LIMITE_DIARIO = int(os.environ.get("LIMITE_DIARIO", "10"))
PORT = int(os.environ.get("PORT", 10000))

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"  # backup file persistence
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"
COOKIES_INSTAGRAM = SCRIPT_DIR / "cookies_ig.txt"

# If env has raw COOKIES_TIKTOK, write to file (preserve existing behavior)
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w", encoding="utf-8") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

# Support two ways of providing Instagram cookies:
# 1) COOKIES_IG_B64 (Base64 encoded content of cookies file) - recommended
# 2) COOKIES_INSTAGRAM (raw cookie file content)
if "COOKIES_IG_B64" in os.environ:
    try:
        decoded = base64.b64decode(os.environ["COOKIES_IG_B64"]).decode("utf-8")
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(decoded)
        print("Cookies Instagram carregados do COOKIES_IG_B64 com sucesso!")
    except Exception as e:
        print("Erro ao decodificar COOKIES_IG_B64:", e)

# Fallback if someone provided COOKIES_INSTAGRAM directly (legacy)
if "COOKIES_INSTAGRAM" in os.environ and not COOKIES_INSTAGRAM.exists():
    try:
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(os.environ["COOKIES_INSTAGRAM"])
        print("Cookies Instagram carregados do env COOKIES_INSTAGRAM.")
    except Exception as e:
        print("Erro ao gravar COOKIES_INSTAGRAM:", e)

# ---------------------------------------------------------
# JSON UTILS
# ---------------------------------------------------------
def load_json(path: Path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------
# SISTEMA DE PREMIUM PERSISTENTE (ENV + fallback arquivo)
# ---------------------------------------------------------

def load_premium_env():
    """
    Carrega PREMIUM_DB do ENV (string JSON) + merge com premium.json.
    Retorna dict {user_id_str: True}
    """
    db = {}

    # 1 — Carrega ENV (se existir)
    raw = os.environ.get("PREMIUM_DB")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                db.update(parsed)
        except Exception as e:
            print("Erro ao parsear PREMIUM_DB:", e)

    # 2 — Merge com arquivo (fallback)
    try:
        file_data = load_json(ARQUIVO_PREMIUM)
        if isinstance(file_data, dict):

            # suporte antigo: {"premium_users": [...]}
            if "premium_users" in file_data:
                for uid in file_data["premium_users"]:
                    db[str(uid)] = True

            else:
                # dict antigo {"123": true, "321": true}
                for k, v in file_data.items():
                    if v:
                        db[str(k)] = True
    except Exception:
        pass

    return db


def save_premium_env(db: dict):
    """
    Salva no arquivo premium.json (persistente sempre).
    Também coloca no ENV para a execução atual.
    No Render Free, somente o arquivo garante persistência entre reinícios.
    """
    try:
        os.environ["PREMIUM_DB"] = json.dumps(db)
    except Exception:
        pass

    # salva backup oficial do bot
    save_json(ARQUIVO_PREMIUM, {"premium_users": [int(k) for k in db.keys()]})


# Banco interno carregado
_premium_db = load_premium_env()


# ---------------------------------------------------------
# PREMIUM MANUAL FIXO (permanente)
# ---------------------------------------------------------
PREMIUM_FIXO = [
    ADMIN_ID,     # Admin sempre premium
    908662411,    # Seu usuário manual
    # Adicione mais aqui:
    # 123456789,
    # 987654321,
]

for uid in PREMIUM_FIXO:
    _premium_db[str(uid)] = True


# Salva tudo junto só UMA vez (evita duplicação)
save_premium_env(_premium_db)


# ---------------------------------------------------------
# FUNÇÕES DE PREMIUM
# ---------------------------------------------------------
def add_premium(user_id):
    uid = str(int(user_id))
    _premium_db[uid] = True
    save_premium_env(_premium_db)


def remove_premium(user_id):
    uid = str(int(user_id))
    if uid in _premium_db:
        del _premium_db[uid]
        save_premium_env(_premium_db)


def is_premium(user_id) -> bool:
    return str(int(user_id)) in _premium_db


def list_premium():
    return sorted(int(k) for k in _premium_db.keys())


# Retrocompatibilidade (se alguém usar variável antiga)
USUARIOS_PREMIUM = set(list_premium())

# ---------------------------------------------------------
# ASAAS — PREMIUM AUTOMÁTICO
# ---------------------------------------------------------
def verificar_pagamentos_asaas():
    try:
        if not ASAAS_API_KEY:
            # print apenas no inicio; não quebra caso não tenha Asaas
            print("Asaas desativado (sem API KEY).")
            return
        url = f"{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()
        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                uid = int(p["metadata"]["telegram_id"])
                add_premium(uid)  # adiciona persistente
    except Exception as e:
        print("Erro Asaas:", e)


# ---------------------------------------------------------
# LIMITE DIÁRIO (corrigido)
# ---------------------------------------------------------
def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())

    # cria estrutura se não existir
    if str(uid) not in data:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)
        return 0

    # se for outro dia, zera o contador
    if data[str(uid)]["data"] != hoje:
        data[str(uid)]["data"] = hoje
        data[str(uid)]["downloads"] = 0
        save_json(ARQUIVO_CONTADOR, data)

    return data[str(uid)]["downloads"]


def incrementar_download(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())

    if str(uid) not in data:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        # se for novo dia, reinicia o contador
        if data[str(uid)]["data"] != hoje:
            data[str(uid)]["data"] = hoje
            data[str(uid)]["downloads"] = 1
        else:
            data[str(uid)]["downloads"] += 1

    save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]


# ---------------------------------------------------------
# COMANDOS
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texto = (
        "🎬 *Jet TikTokShop Bot*\n\n"
        "Envie um link para baixar vídeo.\n"
        "⚠️ Free: 10/dia\n"
        "💎 Premium: ilimitado"
    )
    botoes = [
        [InlineKeyboardButton("💎 Planos", callback_data="planos")],
        [InlineKeyboardButton("🆘 Suporte", callback_data="duvida")],
    ]
    if user_id == ADMIN_ID:
        botoes += [
            [InlineKeyboardButton("➕ Add Premium", callback_data="addpremium")],
            [InlineKeyboardButton("➖ Remover Premium", callback_data="delpremium")],
        ]
    await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💎 1 Mês – R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses – R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano – R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")],
    ]
    # Se chamado por CallbackQuery, responder usando query; se por comando, update.message estará presente
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))


async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("📞 Suporte: lavimurtha@gmail.com")
    else:
        await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")


async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")


# ---------------------------------------------------------
# ADMIN COMANDOS MANUAIS
# ---------------------------------------------------------
async def addpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # se chamado via callback (botão), instruir como usar
    if update.callback_query:
        await update.callback_query.answer()
        return await update.callback_query.message.reply_text("Use /addpremium <user_id> no chat (apenas admin).")

    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /addpremium <user_id>")
    uid = int(context.args[0])
    add_premium(uid)
    await update.message.reply_text(f"✅ Usuário {uid} adicionado ao Premium!")


async def delpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # se chamado via callback (botão), instruir como usar
    if update.callback_query:
        await update.callback_query.answer()
        return await update.callback_query.message.reply_text("Use /delpremium <user_id> no chat (apenas admin).")

    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /delpremium <user_id>")
    uid = int(context.args[0])
    remove_premium(uid)
    await update.message.reply_text(f"❌ Usuário {uid} removido do Premium.")


# ---------------------------------------------------------
# NOVO: /verpremium (listar usuarios premium) - admin
# ---------------------------------------------------------
async def verpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")

    users = list_premium()
    if not users:
        return await update.message.reply_text("Nenhum usuário premium cadastrado.")

    lista = "\n".join(str(uid) for uid in users)
    await update.message.reply_text(f"💎 *Usuários Premium:*\n{lista}", parse_mode="Markdown")


# ---------------------------------------------------------
# SHOPEE UNIVERSAL PATCH 2025
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
        data.get("data", {}).get("play")
        or data.get("data", {}).get("video_url")
        or data.get("data", {}).get("url")
        or (data.get("data", {}).get("videos", [{}])[0].get("url") if data.get("data", {}).get("videos") else None)
        or data.get("data", {}).get("path")
    )
    if not video_url:
        try:
            html = requests.get(url, timeout=10).text
            for regex in [
                r"https?://[^\s\"']+\.mp4",
                r"https?://[^\s\"']+\.m3u8[^\s\"']*",
                r'"url":"(https:[^"]+)"',
                r'"play[^"]*":"(https:[^"]+)"',
            ]:
                match = re.search(regex, html)
                if match:
                    return match.group(1) if len(match.groups()) else match.group(0)
        except:
            pass
    return video_url


# ---------------------------------------------------------
# INSTAGRAM PATCH 2025
# ---------------------------------------------------------
def extrair_video_instagram(url):
    """
    Extrai vídeo do Instagram (post ou story) usando yt-dlp e cookies.
    Funciona para contas públicas e privadas (com cookies válidos no Render).
    """
    try:
        # Limpa a URL de query strings
        clean_url = url.split("?")[0]

        # Opções do yt-dlp
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "format": "best[ext=mp4]/best",
        }

        # Usa cookies do Render (decodificado)
        if not COOKIES_INSTAGRAM.exists() and "COOKIES_IG_B64" in os.environ:
            try:
                decoded = base64.b64decode(os.environ["COOKIES_IG_B64"]).decode("utf-8")
                with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
                    f.write(decoded)
                print("Cookies Instagram carregados do COOKIES_IG_B64 com sucesso!")
            except Exception as e:
                print("Erro ao decodificar COOKIES_IG_B64:", e)

        if COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)

        # Extrai info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)

        # Retorna a URL direta do vídeo
        if info.get("url"):
            return info.get("url")
        elif info.get("requested_formats"):
            # Alguns stories/IGTV usam requested_formats
            return info["requested_formats"][0].get("url")
        elif info.get("entries"):
            # Stories em lista
            return info["entries"][0].get("url")
        else:
            return None

    except Exception as e:
        print("Erro ao extrair vídeo do Instagram:", e)
        return None


# ---------------------------------------------------------
# DOWNLOAD HANDLER (TikTok, Shopee, Instagram, YouTube)
# ---------------------------------------------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.message.from_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    verificar_pagamentos_asaas()

    # usa is_premium() em vez de set direto
    if not is_premium(uid):
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    # Shopee
    if any(x in url for x in ["shopee.com", "shp.ee", "sv.shopee.com"]):
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo da Shopee.")
        url = video_url

    # Instagram
    elif any(x in url for x in ["instagram.com", "instagr.am", "ig.me"]):
        await update.message.reply_text("🔄 Processando link do Instagram...")
        video_url = extrair_video_instagram(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo do Instagram (pode ser privado).")
        url = video_url

    await update.message.reply_text("⏳ Baixando...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        ydl_opts = {
            "outtmpl": output,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
                {"key": "FFmpegMetadata"},
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
            ],
            "postprocessor_args": ["-movflags", "faststart"],
        }

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
        if "instagram" in url and COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)

        def run(url_local):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_local, download=True)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, lambda: run(url))

        # envia vídeo (arquivo local ou url retornado)
        # o ydl.prepare_filename retorna caminho local quando baixou; porém em alguns extratores pode retornar url.
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                await update.message.reply_video(f, caption="✅ Seu vídeo está aqui!")
            try:
                os.remove(file_path)
            except:
                pass
        else:
            # se o extractor retornou uma URL direta em vez de arquivo local
            await update.message.reply_video(file_path, caption="✅ Seu vídeo está aqui!")

        if not is_premium(uid):
            novo = incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {novo}/{LIMITE_DIARIO}")

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")


# ---------------------------------------------------------
# CALLBACKQUERY para botões do menu (planos, duvida, add/del premium instruções)
# ---------------------------------------------------------
async def callbacks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = (query.data or "").lower()
    if data == "planos":
        await planos(update, context)
    elif data == "duvida":
        await duvida(update, context)
    elif data == "addpremium":
        await addpremium(update, context)
    elif data == "delpremium":
        await delpremium(update, context)
    else:
        await query.answer()


# ---------------------------------------------------------
# KEEPALIVE (Render Cold Start fix)
# ---------------------------------------------------------
async def keepalive_task():
    await asyncio.sleep(5)
    while True:
        try:
            host = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("RENDER_EXTERNAL_URL")
            if host:
                # tentativa silenciosa; não falha se der erro
                requests.get(f"https://{host}/webhook", timeout=5)
        except:
            pass
        await asyncio.sleep(300)  # 5 minutos


# ---------------------------------------------------------
# MAIN (WEBHOOK) - sem post_init, set_my_commands direto
# ---------------------------------------------------------
async def main():
    verificar_pagamentos_asaas()

    app = Application.builder().token(TOKEN).build()

    # definir comandos (await pois é coroutine do bot)
    await app.bot.set_my_commands([
        BotCommand("start", "Iniciar bot"),
        BotCommand("planos", "Planos premium"),
        BotCommand("duvida", "Ajuda"),
        BotCommand("meuid", "Mostrar ID"),
        BotCommand("addpremium", "Adicionar premium (admin)"),
        BotCommand("delpremium", "Remover premium (admin)"),
        BotCommand("verpremium", "Visualizar premium (admin)"),
    ])

    # handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(CommandHandler("verpremium", verpremium))
    app.add_handler(CallbackQueryHandler(callbacks_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    # iniciar keepalive background
    asyncio.create_task(keepalive_task())

    print(f"Iniciando bot (webhook) na porta {PORT}...")
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("RENDER_EXTERNAL_URL")
    if not host:
        print("Aviso: RENDER_EXTERNAL_HOSTNAME/RENDER_EXTERNAL_URL não definido; webhook_url pode estar incorreto.")

    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{host}/webhook" if host else None,
    )


# ---------------------------------------------------------
# EXECUÇÃO SEGURA PARA RENDER
# ---------------------------------------------------------
if __name__ == "__main__":
    # evita RuntimeError: This event loop é já executando
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())

