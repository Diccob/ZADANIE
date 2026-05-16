import asyncio
from datetime import datetime, timedelta
from datetime import timezone, timedelta

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

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Екатеринбургское время
EKB_TZ = timezone(timedelta(hours=5))

# Сколько рублей тратится в месяц
MONTHLY_COST = 400

# Сколько примерно затяжек с одной жижки
PUFFS_PER_MONTH = 6000
# Цена одной затяжки
COST_PER_PUFF = round(
    MONTHLY_COST / PUFFS_PER_MONTH,
    4
)

# =========================
# КЛАВИАТУРА
# =========================

def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚬 Затянулся",
                    callback_data="smoke"
                )
            ]
        ]
    )


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def ekb_now():
    return datetime.now(EKB_TZ)


async def get_today_count(user_id):

    today = ekb_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:

        cursor = await db.execute(
            """
            SELECT COUNT(*)
            FROM smokes
            WHERE user_id = ?
            AND date LIKE ?
            """,
            (user_id, f"{today}%")
        )

        result = await cursor.fetchone()

        return result[0]


async def get_yesterday_count(user_id):

    yesterday = (
        ekb_now() - timedelta(days=1)
    ).strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:

        cursor = await db.execute(
            """
            SELECT COUNT(*)
            FROM smokes
            WHERE user_id = ?
            AND date LIKE ?
            """,
            (user_id, f"{yesterday}%")
        )

        result = await cursor.fetchone()

        return result[0]


async def get_month_count(user_id):

    month = ekb_now().strftime("%Y-%m")

    async with aiosqlite.connect(DB_NAME) as db:

        cursor = await db.execute(
            """
            SELECT COUNT(*)
            FROM smokes
            WHERE user_id = ?
            AND date LIKE ?
            """,
            (user_id, f"{month}%")
        )

        result = await cursor.fetchone()

        return result[0]


async def get_all_users():

    async with aiosqlite.connect(DB_NAME) as db:

        cursor = await db.execute(
            """
            SELECT DISTINCT user_id
            FROM smokes
            """
        )

        result = await cursor.fetchall()

        return [row[0] for row in result]


# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):

    await message.answer(
        "🚬 Нажми кнопку если затянулся",
        reply_markup=main_keyboard()
    )


# =========================
# КНОПКА ЗАТЯЖКИ
# =========================

@dp.callback_query(F.data == "smoke")
async def smoke(callback: CallbackQuery):

    now = ekb_now().strftime("%Y-%m-%d %H:%M:%S")

    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute(
            """
            INSERT INTO smokes (user_id, date)
            VALUES (?, ?)
            """,
            (user_id, now)
        )

        await db.commit()

    today = await get_today_count(user_id)
    month = await get_month_count(user_id)

# Цена одной затяжки
    cost_per_puff = round(
        MONTHLY_COST / PUFFS_PER_MONTH,
        4
    )

# Потрачено
    spent_today = round(
        today * cost_per_puff,
        2
    )

    spent_month = round(
        month * cost_per_puff,
        2
    )

    # =========================
    # СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЮ
    # =========================

    await callback.message.edit_text(
        f"🚬 Записал\n\n"
        f"📅 Сегодня: {today}\n"
        f"🗓 За месяц: {month}\n\n"
        f"💸 Потрачено сегодня: {spent_today}₽\n"
        f"💰 Потрачено за месяц: {spent_month}₽",
        reply_markup=main_keyboard()
    )

    # =========================
    # УВЕДОМЛЕНИЕ АДМИНУ
    # =========================

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
# ЕЖЕДНЕВНАЯ СВОДКА
# =========================

async def daily_report_loop():

    while True:

        now = ekb_now()

        if now.hour == 0 and now.minute == 0:

            users = await get_all_users()

            for user_id in users:

                today = await get_today_count(user_id)
                yesterday = await get_yesterday_count(user_id)

                difference = today - yesterday

                if difference < 0:

                    diff_text = (
                        f"🔥 Меньше на "
                        f"{abs(difference)} затяжек"
                    )

                elif difference > 0:

                    diff_text = (
                        f"⚠️ Больше на "
                        f"{difference} затяжек"
                    )

                else:

                    diff_text = (
                        "➖ Столько же, сколько вчера"
                    )

                text = (
                    f"📊 Сводка за день\n\n"
                    f"🚬 Сегодня: {today}\n"
                    f"🚬 Вчера: {yesterday}\n\n"
                    f"{diff_text}"
                )

                # Пользователю
                await bot.send_message(user_id, text)

                # Админу
                await bot.send_message(
                    OWNER_ID,
                    f"📨 Отчёт пользователя\n\n{text}"
                )

            # защита от спама
            await asyncio.sleep(60)

        await asyncio.sleep(15)


# =========================
# МЕСЯЧНАЯ СВОДКА
# =========================

async def month_report_loop():

    while True:

        now = ekb_now()

        if (
            now.day == 1 and
            now.hour == 0 and
            now.minute == 0
        ):

            users = await get_all_users()

            for user_id in users:

                month = await get_month_count(user_id)

                text = (
                    f"📅 Сводка за месяц\n\n"
                    f"🚬 Всего затяжек: {month}\n"
                    f"💸 Потрачено: {MONTHLY_COST}₽"
                )

                # Пользователю
                await bot.send_message(user_id, text)

                # Админу
                await bot.send_message(
                    OWNER_ID,
                    f"📨 Месячный отчёт\n\n{text}"
                )

            await asyncio.sleep(60)

        await asyncio.sleep(15)

# =========================
# НАПОМИНАНИЯ
# =========================

async def reminder_loop():

    while True:

        users = await get_all_users()

        for user_id in users:

            try:

                await bot.send_message(
                    user_id,
                    "⏰ Не забывай отмечать затяжки"
                )

            except Exception as e:

                print(
                    f"Ошибка отправки "
                    f"напоминания: {e}"
                )

        # 3 часа
        await asyncio.sleep(10800)

# =========================
# MAIN
# =========================

async def main():

    await init_db()

    print("Бот запущен")

    asyncio.create_task(daily_report_loop())
    asyncio.create_task(month_report_loop())
    asyncio.create_task(reminder_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
