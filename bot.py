import asyncio
import logging
import os
import random
import aiohttp
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Кэш прокси
proxy_pool = []
broken_ids = set()
used_ids = set()
last_sent = {}

async def fetch_proxies() -> list:
    """Парсит свежие прокси с mtpro.xyz"""
    proxies = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://mtpro.xyz/api/?type=mtproto",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                for item in data:
                    proxies.append({
                        "server": item["host"],
                        "port": item["port"],
                        "secret": item["secret"]
                    })
        logger.info(f"Загружено прокси: {len(proxies)}")
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
    return proxies

async def refresh_pool():
    """Обновляет пул прокси каждые 30 минут"""
    global proxy_pool, used_ids
    while True:
        new = await fetch_proxies()
        if new:
            proxy_pool = new
            used_ids.clear()  # Сбрасываем использованные при обновлении
            logger.info(f"Пул обновлён: {len(proxy_pool)} прокси")
        await asyncio.sleep(1800)  # 30 минут

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
    if edit_message:
        await edit_message.edit_text(text, reply_markup=get_keyboard())
    else:
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
    logger.info("Загружаю первый пул прокси...")
    global proxy_pool
    proxy_pool = await fetch_proxies()
    asyncio.create_task(refresh_pool())

async def main():
    dp.startup.register(on_startup)
    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
