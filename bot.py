import random
import asyncio
import os  # ← ДОБАВИТЬ
from datetime import datetime, timedelta, timezone
from aiohttp import web
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application
)
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

import aiosqlite

from config import TOKEN, OWNER_ID
from database import init_db, DB_NAME

# =========================
# НАСТРОЙКИ
# =========================

# 🔥 КРИТИЧНО: абсолютный путь к базе и файлам
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Если DB_NAME в database.py относительный — переопределяем здесь
if not os.path.isabs(DB_NAME):
    DB_NAME = os.path.join(BASE_DIR, DB_NAME)

IMAGES_DIR = os.path.join(BASE_DIR, "images")

bot = Bot(token=TOKEN)
dp = Dispatcher()
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = "https://nl8.bothost.ru/webhook"

WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 8080

EKB_TZ = timezone(timedelta(hours=5))
MONTHLY_COST = 400
PUFFS_PER_MONTH = 6000
COST_PER_PUFF = round(MONTHLY_COST / PUFFS_PER_MONTH, 4)
BASELINE_WEEKLY_PUFFS = 3900

# =========================
# КЛАВИАТУРА
# =========================

def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚬 Затянулся", callback_data="smoke")]
        ]
    )

# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def ekb_now():
    return datetime.now(EKB_TZ)

async def get_day_count(user_id, days_ago=0):
    target_day = (ekb_now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM smokes WHERE user_id = ? AND date LIKE ?",
            (user_id, f"{target_day}%")
        )
        result = await cursor.fetchone()
        return result[0]

async def get_month_count(user_id, months_ago=0):
    now = ekb_now()
    # 🔥 Исправлен расчёт месяца (было неточно с timedelta)
    month = now.month - months_ago
    year = now.year
    while month < 1:
        month += 12
        year -= 1
    target_month = f"{year}-{month:02d}"
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM smokes WHERE user_id = ? AND date LIKE ?",
            (user_id, f"{target_month}%")
        )
        result = await cursor.fetchone()
        return result[0]

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT DISTINCT user_id FROM smokes")
        result = await cursor.fetchall()
        return [row[0] for row in result]

# =========================
# HANDLERS
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer("🚬 Нажми кнопку если затянулся", reply_markup=main_keyboard())

@dp.callback_query(F.data == "smoke")
async def smoke(callback: CallbackQuery):
    now = ekb_now().strftime("%Y-%m-%d %H:%M:%S")
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO smokes (user_id, date) VALUES (?, ?)", (user_id, now))
        await db.commit()

    today = await get_day_count(user_id, 0)
    month = await get_month_count(user_id)
    spent_today = round(today * COST_PER_PUFF, 2)
    spent_month = round(month * COST_PER_PUFF, 2)

    try:
        await callback.message.edit_text(
            f"🚬 Записал\n\n"
            f"📅 Сегодня: {today}\n"
            f"🗓 За месяц: {month}\n\n"
            f"💸 Потрачено сегодня: {spent_today}₽\n"
            f"💰 Потрачено за месяц: {spent_month}₽",
            reply_markup=main_keyboard()
        )
    except Exception:
        pass

    await bot.send_message(
        OWNER_ID,
        f"🚨 Новая затяжка\n\n"
        f"👤 Пользователь: {first_name}\n"
        f"📎 Username: @{username}\n\n"
        f"🚬 Сегодня: {today}\n"
        f"📅 За месяц: {month}\n"
        f"💸 Сегодня потрачено: {spent_today}₽\n"
        f"⏰ Время: {ekb_now().strftime('%H:%M')}"
    )
    await callback.answer()

# =========================
# ФОНОВЫЕ ЗАДАЧИ
# =========================

async def daily_report_loop():
    while True:
        try:
            now = ekb_now()
            if now.hour == 0 and now.minute == 0:
                users = await get_all_users()
                for user_id in users:
                    today = await get_day_count(user_id, 1)
                    yesterday = await get_day_count(user_id, 2)
                    
                    if yesterday == 0 and today != 0:
                        yesterday = 400
                    difference = today - yesterday
                    percent = round((abs(difference) / yesterday) * 100, 1) if yesterday else 0
                    
                    if difference < 0:
                        result = f"🔥 На {percent}% меньше затяжек"
                        photo = os.path.join(IMAGES_DIR, "win.jpg")
                    elif difference > 0:
                        result = f"⚠️ На {percent}% больше затяжек"
                        photo = os.path.join(IMAGES_DIR, "lose.jpg")
                    else:
                        result = "➖ Столько же, сколько вчера"
                        photo = os.path.join(IMAGES_DIR, "equal.jpg")
                    
                    text = f"📊 Сводка за день\n\n🚬 Сегодня: {today}\n🚬 Вчера: {yesterday}\n\n{result}"
                    
                    try:
                        with open(photo, "rb") as img:
                            await bot.send_photo(user_id, photo=img, caption=text)
                    except Exception as e:
                        print(f"photo error: {e}")
                    
                    try:
                        with open(photo, "rb") as img:
                            await bot.send_photo(OWNER_ID, photo=img, caption=f"📨 Отчёт пользователя\n\n{text}")
                    except Exception as e:
                        print(f"admin photo error: {e}")
                await asyncio.sleep(60)
        except Exception as e:
            print(f"daily_report_loop error: {e}")
            await asyncio.sleep(5)
        await asyncio.sleep(15)

async def month_report_loop():
    while True:
        try:
            now = ekb_now()
            if now.day == 1 and now.hour == 0 and now.minute == 0:
                users = await get_all_users()
                for user_id in users:
                    month_count = await get_month_count(user_id, 1)
                    text = f"📅 Сводка за месяц\n\n🚬 Всего затяжек: {month_count}\n💸 Потрачено: {MONTHLY_COST}₽"
                    await bot.send_message(user_id, text)
                    await bot.send_message(OWNER_ID, f"📨 Месячный отчёт\n\n{text}")
                await asyncio.sleep(60)
        except Exception as e:
            print(f"month_report_loop error: {e}")
            await asyncio.sleep(5)
        await asyncio.sleep(15)

async def reminder_loop():
    while True:
        try:
            # 🔥 Исправлено: один долгий sleep вместо 10800 коротких
            await asyncio.sleep(3 * 3600)
            users = await get_all_users()
            for user_id in users:
                try:
                    await bot.send_message(user_id, "⏰ Не забывай отмечать затяжки")
                    await asyncio.sleep(0.05)
                except Exception as e:
                    print(f"Ошибка отправки напоминания пользователю {user_id}: {e}")
        except Exception as e:
            print(f"reminder_loop error: {e}")
            await asyncio.sleep(5)

async def get_week_count(user_id, weeks_ago=0):
    now = ekb_now()
    start_of_week = now - timedelta(days=now.weekday())
    target_week_start = start_of_week - timedelta(weeks=weeks_ago)
    total = 0
    async with aiosqlite.connect(DB_NAME) as db:
        for i in range(7):
            day = (target_week_start + timedelta(days=i)).strftime("%Y-%m-%d")
            cursor = await db.execute(
                "SELECT COUNT(*) FROM smokes WHERE user_id = ? AND date LIKE ?",
                (user_id, f"{day}%")
            )
            result = await cursor.fetchone()
            total += result[0]
    return total

async def weekly_report_loop():
    while True:
        try:
            now = ekb_now()
            if now.weekday() == 0 and now.hour == 0 and now.minute == 0:
                users = await get_all_users()
                for user_id in users:
                    current_week = await get_week_count(user_id, 1)
                    previous_week = await get_week_count(user_id, 2)
                    if previous_week == 0:
                        previous_week = BASELINE_WEEKLY_PUFFS
                    difference = current_week - previous_week
                    percent = round((difference / previous_week) * 100, 1)
                    
                    if percent < 0:
                        result = f"🔥 На {abs(percent)}% меньше затяжек"
                    elif percent > 0:
                        result = f"⚠️ На {percent}% больше затяжек"
                    else:
                        result = "➖ Без изменений"
                    
                    text = f"📈 Недельная статистика\n\n🚬 Прошедшая неделя: {current_week}\n🚬 Позапрошлая неделя: {previous_week}\n\n{result}"
                    try:
                        await bot.send_message(user_id, text)
                        await bot.send_message(OWNER_ID, f"📨 Недельный отчёт\n\n{text}")
                        await asyncio.sleep(0.05)
                    except Exception as e:
                        print(f"Ошибка отправки недельного отчёта: {e}")
                await asyncio.sleep(60)
        except Exception as e:
            print(f"weekly_report_loop error: {e}")
            await asyncio.sleep(5)
        await asyncio.sleep(15)

async def heartbeat():
    while True:
        print("heartbeat")
        await asyncio.sleep(60)

# =========================
# WEBHOOK & SERVER
# =========================

async def on_startup(app):
    await init_db()
    print("Бот запущен")
    
    # Запускаем фоновые задачи
    asyncio.create_task(daily_report_loop())
    asyncio.create_task(month_report_loop())
    asyncio.create_task(reminder_loop())
    asyncio.create_task(weekly_report_loop())
    asyncio.create_task(heartbeat())
    
    # Устанавливаем webhook
    try:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        info = await bot.get_webhook_info()
        print(f"✓ Webhook установлен: {info.url}")
    except Exception as e:
        print(f"✗ Ошибка установки webhook: {e}")

async def on_shutdown(app):
    print("Бот останавливается")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()
    # Больше ничего не нужно — aiogram сам завершит диспетчер

def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    print(f"Запуск сервера на {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)

if __name__ == "__main__":
    main()
