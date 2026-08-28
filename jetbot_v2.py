import asyncio
import base64
import json
import os
import re
import shutil
import tempfile
import traceback
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import requests
import yt_dlp
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv('TOKEN') or os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_TOKEN') or os.getenv('TG_BOT_TOKEN')
if not TOKEN:
    raise ValueError('Configure TOKEN ou BOT_TOKEN no Render.')

ASAAS_API_KEY = os.getenv('ASAAS_API_KEY')
ASAAS_BASE_URL = 'https://www.asaas.com/api/v3'
ADMIN_ID = int(os.getenv('ADMIN_ID', '5593153639'))
LIMITE_DIARIO = int(os.getenv('LIMITE_DIARIO', '10'))
PORT = int(os.getenv('PORT', '10000'))
MAX_FILE_MB = int(os.getenv('MAX_FILE_MB', '49'))

ROOT = Path(__file__).resolve().parent
DOWNLOADS_DIR = ROOT / 'downloads'
DOWNLOADS_DIR.mkdir(exist_ok=True)
ARQUIVO_CONTADOR = ROOT / 'downloads.json'
ARQUIVO_PREMIUM = ROOT / 'premium.json'

PLATFORM_NAMES = {
    'instagram': 'Instagram', 'tiktok': 'TikTok', 'twitter': 'X/Twitter',
    'youtube': 'YouTube/Shorts', 'shopee': 'Shopee Vídeo', 'pinterest': 'Pinterest',
    'facebook': 'Facebook', 'reddit': 'Reddit', 'vimeo': 'Vimeo', 'generic': 'vídeo'
}


def load_json(path: Path):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_premium_env():
    db = {}
    raw = os.getenv('PREMIUM_DB')
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                db.update({str(k): bool(v) for k, v in parsed.items() if v})
        except Exception as exc:
            print('PREMIUM_DB inválido:', exc)
    file_data = load_json(ARQUIVO_PREMIUM)
    if isinstance(file_data, dict):
        users = file_data.get('premium_users')
        if isinstance(users, list):
            for uid in users:
                db[str(uid)] = True
        else:
            for uid, enabled in file_data.items():
                if enabled:
                    db[str(uid)] = True
    return db


def persist_premium(db):
    try:
        os.environ['PREMIUM_DB'] = json.dumps(db)
    except Exception:
        pass
    ids = []
    for key in db:
        try:
            ids.append(int(key))
        except ValueError:
            continue
    save_json(ARQUIVO_PREMIUM, {'premium_users': sorted(ids)})


_premium_db = load_premium_env()
PREMIUM_FIXO = {str(ADMIN_ID), '908662411'}
for _uid in PREMIUM_FIXO:
    _premium_db[_uid] = True
persist_premium(_premium_db)


def is_premium(user_id): return str(int(user_id)) in _premium_db

def add_premium(user_id):
    _premium_db[str(int(user_id))] = True
    persist_premium(_premium_db)

def remove_premium(user_id):
    uid = str(int(user_id))
    if uid not in PREMIUM_FIXO:
        _premium_db.pop(uid, None)
    persist_premium(_premium_db)

def get_premium_status():
    return set(PREMIUM_FIXO), set(_premium_db) - set(PREMIUM_FIXO)


def verificar_pagamentos_asaas():
    if not ASAAS_API_KEY:
        return
    try:
        response = requests.get(
            f'{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100',
            headers={'access_token': ASAAS_API_KEY}, timeout=10
        )
        response.raise_for_status()
        for payment in response.json().get('data', []):
            telegram_id = (payment.get('metadata') or {}).get('telegram_id')
            if telegram_id:
                add_premium(int(telegram_id))
    except Exception as exc:
        print('Erro Asaas:', exc)


def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    item = data.get(str(uid), {'data': hoje, 'downloads': 0})
    if item.get('data') != hoje:
        item = {'data': hoje, 'downloads': 0}
    data[str(uid)] = item
    save_json(ARQUIVO_CONTADOR, data)
    return int(item.get('downloads', 0))


def incrementar_download(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    item = data.get(str(uid), {'data': hoje, 'downloads': 0})
    if item.get('data') != hoje:
        item = {'data': hoje, 'downloads': 0}
    item['downloads'] = int(item.get('downloads', 0)) + 1
    item['data'] = hoje
    data[str(uid)] = item
    save_json(ARQUIVO_CONTADOR, data)
    return item['downloads']


def detect_platform(url: str):
    host = url.lower()
    checks = [
        ('instagram', ('instagram.com', 'instagr.am')),
        ('tiktok', ('tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com')),
        ('twitter', ('twitter.com', 'x.com')),
        ('youtube', ('youtube.com', 'youtu.be')),
        ('shopee', ('shopee.com', 'shp.ee', 'sv.shopee.com')),
        ('pinterest', ('pinterest.', 'pin.it')),
        ('facebook', ('facebook.com', 'fb.watch')),
        ('reddit', ('reddit.com', 'redd.it')),
        ('vimeo', ('vimeo.com',)),
    ]
    for name, domains in checks:
        if any(domain in host for domain in domains):
            return name
    return 'generic'


def _write_cookie_from_env(platform: str, temp_dir: Path):
    aliases = {
        'instagram': ('COOKIES_INSTAGRAM', 'COOKIES_IG_B64'),
        'tiktok': ('COOKIES_TIKTOK', 'COOKIES_TIKTOK_B64'),
        'youtube': ('COOKIES_YOUTUBE', 'COOKIES_YT_B64'),
        'twitter': ('COOKIES_TWITTER', 'COOKIES_X_B64'),
        'shopee': ('COOKIES_SHOPEE', 'COOKIES_SHOPEE_B64'),
        'pinterest': ('COOKIES_PINTEREST', 'COOKIES_PINTEREST_B64'),
        'facebook': ('COOKIES_FACEBOOK', 'COOKIES_FACEBOOK_B64'),
        'reddit': ('COOKIES_REDDIT', 'COOKIES_REDDIT_B64'),
        'vimeo': ('COOKIES_VIMEO', 'COOKIES_VIMEO_B64'),
    }
    plain_key, b64_key = aliases.get(platform, (f'COOKIES_{platform.upper()}', f'COOKIES_{platform.upper()}_B64'))
    payload = os.getenv(plain_key)
    if not payload and os.getenv(b64_key):
        try:
            payload = base64.b64decode(os.getenv(b64_key)).decode('utf-8')
        except Exception as exc:
            print(f'Cookie B64 inválido para {platform}:', exc)
    generic_b64 = os.getenv('COOKIES_B64')
    if not payload and generic_b64:
        try:
            payload = base64.b64decode(generic_b64).decode('utf-8')
        except Exception:
            pass
    if not payload:
        return None
    cookie_path = temp_dir / f'cookies-{platform}.txt'
    cookie_path.write_text(payload, encoding='utf-8')
    return str(cookie_path)


def _resolve_shopee(url: str):
    if 'shp.ee' in url:
        try:
            url = requests.get(url, allow_redirects=True, timeout=10).url
        except Exception:
            pass
    if 'redir=' in url:
        match = re.search(r'redir=([^&]+)', url)
        if match:
            url = unquote(match.group(1))
    return url


def download_media(url: str, uid: int):
    platform = detect_platform(url)
    if platform == 'shopee':
        url = _resolve_shopee(url)
    temp_dir = Path(tempfile.mkdtemp(prefix=f'jetbot-{uid}-', dir=DOWNLOADS_DIR))
    cookiefile = _write_cookie_from_env(platform, temp_dir)
    output = str(temp_dir / '%(title).120B-%(id)s.%(ext)s')
    opts = {
        'outtmpl': output,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'restrictfilenames': True,
        'merge_output_format': 'mp4',
        'format': 'bv*[height<=1080]+ba/b[height<=1080]/b',
        'format_sort': ['res:1080', 'ext:mp4:m4a'],
        'retries': 3,
        'fragment_retries': 3,
        'socket_timeout': 25,
        'nocheckcertificate': False,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
    }
    if cookiefile:
        opts['cookiefile'] = cookiefile
    if platform in {'instagram', 'tiktok', 'twitter', 'facebook', 'reddit'}:
        opts['http_headers'] = {'User-Agent': 'Mozilla/5.0'}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            candidate = Path(ydl.prepare_filename(info))
            files = [p for p in temp_dir.iterdir() if p.is_file() and not p.name.startswith('cookies-')]
            if candidate.exists():
                filepath = candidate
            else:
                mp4s = [p for p in files if p.suffix.lower() == '.mp4']
                filepath = (mp4s or files)[0] if files else None
            if not filepath or not filepath.exists():
                raise RuntimeError('Arquivo final não encontrado.')
            return {'path': str(filepath), 'platform': platform, 'title': info.get('title') or 'Vídeo', 'temp_dir': str(temp_dir)}
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = (
        '🎬 *JetBot V2*\n\n'
        'Baixe vídeos públicos de Instagram, TikTok, X/Twitter, YouTube/Shorts, Shopee Vídeo, Pinterest, Facebook, Reddit e Vimeo.\n\n'
        f'⚠️ Free: {LIMITE_DIARIO}/dia\n💎 Premium: ilimitado'
    )
    buttons = [[InlineKeyboardButton('💎 Planos', callback_data='planos')], [InlineKeyboardButton('🆘 Suporte', callback_data='duvida')]]
    if uid == ADMIN_ID:
        buttons += [[InlineKeyboardButton('➕ Add Premium', callback_data='addpremium')], [InlineKeyboardButton('➖ Remover Premium', callback_data='delpremium')]]
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons))


async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton('💎 1 Mês – R$ 9,90', url='https://www.asaas.com/c/knu5vub6ejc2yyja')],
        [InlineKeyboardButton('💎 3 Meses – R$ 25,90', url='https://www.asaas.com/c/o9pg4uxrpgwnmqzd')],
        [InlineKeyboardButton('💎 1 Ano – R$ 89,90', url='https://www.asaas.com/c/puto9coszhwgprqc')],
    ]
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text('💎 Planos Premium:', reply_markup=InlineKeyboardMarkup(kb))


async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text('📞 Suporte: lavimurtha@gmail.com')


async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f'🆔 Seu ID: {update.effective_user.id}')


async def addpremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text('🚫 Apenas o admin pode usar este comando.')
    if not context.args:
        return await update.message.reply_text('Uso: /addpremium <user_id>')
    add_premium(int(context.args[0]))
    await update.message.reply_text(f'✅ Usuário {context.args[0]} adicionado ao Premium!')


async def delpremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text('🚫 Apenas o admin pode usar este comando.')
    if not context.args:
        return await update.message.reply_text('Uso: /delpremium <user_id>')
    remove_premium(int(context.args[0]))
    await update.message.reply_text(f'❌ Usuário {context.args[0]} removido do Premium.')


async def verpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text('🚫 Apenas o admin pode usar este comando.')
    fixos, dinamicos = get_premium_status()
    text = '💎 *Usuários Premium:*\n\n📌 *Fixos:*\n' + ('\n'.join(sorted(fixos)) or 'Nenhum')
    text += '\n\n⚡ *Dinâmicos:*\n' + ('\n'.join(sorted(dinamicos)) or 'Nenhum')
    await update.message.reply_text(text, parse_mode='Markdown')


async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or '').strip()
    uid = update.effective_user.id
    if not re.match(r'^https?://', url, flags=re.I):
        return await update.message.reply_text('❌ Envie um link válido começando com http:// ou https://.')

    verificar_pagamentos_asaas()
    if not is_premium(uid) and verificar_limite(uid) >= LIMITE_DIARIO:
        return await update.message.reply_text('⚠️ Limite diário atingido. Veja /start para conhecer o Premium.')

    platform = detect_platform(url)
    status = await update.message.reply_text(f'⏳ Baixando de {PLATFORM_NAMES[platform]}...')
    result = None
    try:
        result = await asyncio.to_thread(download_media, url, uid)
        path = Path(result['path'])
        if path.stat().st_size > MAX_FILE_MB * 1024 * 1024:
            await status.edit_text(f'⚠️ O arquivo ficou maior que {MAX_FILE_MB} MB e não pode ser enviado por este bot.')
            return
        await status.edit_text('📤 Enviando para o Telegram...')
        with path.open('rb') as media:
            await update.message.reply_video(media, caption=f"✅ {result['title'][:80]}", supports_streaming=True)
        if not is_premium(uid):
            used = incrementar_download(uid)
            await update.message.reply_text(f'📊 Uso diário: {used}/{LIMITE_DIARIO}')
        await status.delete()
    except yt_dlp.utils.DownloadError as exc:
        text = str(exc)
        if 'cookies' in text.lower() or 'login' in text.lower() or 'sign in' in text.lower():
            text = 'A plataforma exigiu autenticação/cookies. Configure os cookies apenas nas variáveis secretas do Render.'
        else:
            text = 'Não foi possível baixar esse link. Ele pode ser privado, removido, protegido ou ainda não suportado pelo extrator atual.'
        await status.edit_text(f'❌ {text}')
    except Exception as exc:
        traceback.print_exc()
        await status.edit_text(f'❌ Erro ao processar o vídeo: {type(exc).__name__}.')
    finally:
        if result and result.get('temp_dir'):
            shutil.rmtree(result['temp_dir'], ignore_errors=True)


async def callbacks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == 'planos': return await planos(update, context)
    if data == 'duvida': return await duvida(update, context)
    await update.callback_query.answer()
    if data == 'addpremium':
        return await update.callback_query.message.reply_text('Use: /addpremium <user_id>')
    if data == 'delpremium':
        return await update.callback_query.message.reply_text('Use: /delpremium <user_id>')


async def keepalive_task():
    while True:
        url = os.getenv('RENDER_EXTERNAL_URL')
        if url:
            try:
                await asyncio.to_thread(requests.get, url, timeout=5)
            except Exception:
                pass
        await asyncio.sleep(240)


async def main():
    verificar_pagamentos_asaas()
    app = Application.builder().token(TOKEN).build()
    await app.bot.set_my_commands([
        BotCommand('start', 'Iniciar o bot'), BotCommand('meuid', 'Mostrar seu ID'),
        BotCommand('addpremium', 'Adicionar usuário premium (admin)'), BotCommand('delpremium', 'Remover usuário premium (admin)'),
        BotCommand('verpremium', 'Listar usuários premium (admin)'),
    ])
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('meuid', meuid))
    app.add_handler(CommandHandler('addpremium', addpremium_cmd))
    app.add_handler(CommandHandler('delpremium', delpremium_cmd))
    app.add_handler(CommandHandler('verpremium', verpremium))
    app.add_handler(CallbackQueryHandler(callbacks_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))
    asyncio.create_task(keepalive_task())

    url = os.getenv('RENDER_EXTERNAL_URL')
    if url:
        await app.run_webhook(listen='0.0.0.0', port=PORT, url_path=TOKEN, webhook_url=f'{url}/{TOKEN}')
    else:
        await app.run_polling()


if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
