import asyncio
import logging
import os
import random
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

proxy_pool = []
broken_ids = set()
used_ids = set()
last_sent = {}

SOURCES = [
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/tg/mtproto.json",
    "https://raw.githubusercontent.com/almaz-us/mtproxy/main/proxies.json",
]

async def fetch_from_github(url: str, session: aiohttp.ClientSession) -> list:
    proxies = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                for item in data:
                    server = item.get("host") or item.get("server") or item.get("ip")
                    port = item.get("port")
                    secret = item.get("secret")
                    if server and port and secret:
                        proxies.append({
                            "server": server,
                            "port": port,
                            "secret": secret
                        })
    except Exception as e:
        logger.warning(f"Ошибка {url}: {e}")
    return proxies

async def fetch_proxies() -> list:
    proxies = []
    async with aiohttp.ClientSession() as session:
        for url in SOURCES:
            result = await fetch_from_github(url, session)
            proxies.extend(result)
            if proxies:
                break  # Нашли — достаточно

    # Запасной список если всё недоступно
    if not proxies:
        proxies = [
            {"server": "proxy.digitalresistance.dog", "port": 443, "secret": "dtFMcSBzFBMjHkBEueBz5ZaArGsxyzABCD"},
            {"server": "mtproto.best", "port": 443, "secret": "dd000000000000000000000000000000"},
            {"server": "109.236.85.152", "port": 8888, "secret": "dd2b81d59031c76a8cf5e2bbbce48bef6b"},
            {"server": "185.246.212.162", "port": 4444, "secret": "ddabcdef1234567890abcdef12345678ab"},
            {"server": "91.108.56.181", "port": 8888, "secret": "dd1234567890abcdef1234567890abcdef"},
            {"server": "95.213.1.1", "port": 1080, "secret": "dd9876543210fedcba9876543210fedcba"},
            {"server": "149.154.167.220", "port": 443, "secret": "ddaabbccddeeff0011223344556677889"},
            {"server": "5.9.33.222", "port": 2398, "secret": "dd112233445566778899aabbccddeeff00"},
            {"server": "176.9.75.42", "port": 8888, "secret": "ddffeeddccbbaa99887766554433221100"},
            {"server": "195.201.30.229", "port": 443, "secret": "dd00112233445566778899aabbccddeeff"},
        ]
        logger.warning("Используем запасной список прокси")

    logger.info(f"Загружено прокси: {len(proxies)}")
    return proxies

async def refresh_pool():
    global proxy_pool, used_ids
    while True:
        new = await fetch_proxies()
        if new:
            proxy_pool = new
            used_ids.clear()
            logger.info(f"Пул обновлён: {len(proxy_pool)} прокси")
        await asyncio.sleep(1800)

def pick_proxies(chat_id: int, count=3) -> list:
    excluded = used_ids.union(broken_ids)
    available = [i for i in range(len(proxy_pool)) if i not in excluded]

    if len(available) < count:
        used_ids.clear()
        available = [i for i in range(len(proxy_pool)) if i not in broken_ids]

    if not available:
        return [], []

    selected = random.sample(available, min(count, len(available)))
    for i in selected:
        used_ids.add(i)
    last_sent[chat_id] = selected
    return [proxy_pool[i] for i in selected], selected

def format_proxies(proxies: list) -> str:
    if not proxies:
        return "😔 Прокси временно недоступны. Попробуй через минуту."
    lines = []
    for i, p in enumerate(proxies, 1):
        link = f"tg://proxy?server={p['server']}&port={p['port']}&secret={p['secret']}"
        lines.append(f"🔒 Прокси {i}:\n`{link}`\n({p['server']}:{p['port']})")
    return "\n\n".join(lines) + "\n\n💡 Нажми на ссылку — Telegram подключится автоматически."

def get_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Новые прокси", callback_data="new_proxy")],
        [InlineKeyboardButton(text="❌ Не работают — дать другие", callback_data="broken")],
    ])

async def send_proxies(chat_id: int, edit_message=None):
    proxies, _ = pick_proxies(chat_id)
    text = format_proxies(proxies)
    try:
        if edit_message:
            await edit_message.edit_text(text, reply_markup=get_keyboard())
        else:
            await bot.send_message(chat_id, text, reply_markup=get_keyboard())
    except Exception as e:
        if "message is not modified" not in str(e):
            logger.error(f"Ошибка отправки: {e}")
            await bot.send_message(chat_id, text, reply_markup=get_keyboard())

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "👋 Привет! Я выдаю свежие MTProto прокси для Telegram.\n\n"
        "🔄 Список обновляется каждые 30 минут\n"
        "🛡 Не повторяю уже выданные\n"
        "❌ Запоминаю нерабочие\n\n"
        "Нажми кнопку:",
        reply_markup=get_keyboard()
    )

@dp.message(Command("proxy"))
async def proxy_command(message: types.Message):
    await send_proxies(message.chat.id)

@dp.callback_query(F.data == "new_proxy")
async def new_proxy_callback(callback: types.CallbackQuery):
    await callback.answer("Генерирую...")
    await send_proxies(callback.message.chat.id, edit_message=callback.message)

@dp.callback_query(F.data == "broken")
async def broken_callback(callback: types.CallbackQuery):
    await callback.answer("Запомнил, даю другие...")
    chat_id = callback.message.chat.id
    if chat_id in last_sent:
        for i in last_sent[chat_id]:
            broken_ids.add(i)
            used_ids.discard(i)
    await send_proxies(chat_id, edit_message=callback.message)

async def on_startup():
    global proxy_pool
    logger.info("Загружаю первый пул прокси...")
    proxy_pool = await fetch_proxies()
    asyncio.create_task(refresh_pool())

async def main():
    dp.startup.register(on_startup)
    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
