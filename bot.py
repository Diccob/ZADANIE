import random
import asyncio
from datetime import datetime, timedelta, timezone

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
BASELINE_WEEKLY_PUFFS = 3900
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


async def get_day_count(user_id, days_ago=0):

    target_day = (
        ekb_now() - timedelta(days=days_ago)
    ).strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:

        cursor = await db.execute(
            """
            SELECT COUNT(*)
            FROM smokes
            WHERE user_id = ?
            AND date LIKE ?
            """,
            (user_id, f"{target_day}%")
        )

        result = await cursor.fetchone()

        return result[0]

async def get_month_count(user_id, months_ago=0):

    now = ekb_now()

    target_month = (
        now.replace(day=1) -
        timedelta(days=30 * months_ago)
    ).strftime("%Y-%m")

    async with aiosqlite.connect(DB_NAME) as db:

        cursor = await db.execute(
            """
            SELECT COUNT(*)
            FROM smokes
            WHERE user_id = ?
            AND date LIKE ?
            """,
            (user_id, f"{target_month}%")
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
    username = callback.from_user.username or "нет"
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

    today = await get_day_count(user_id, 0)
    month = await get_month_count(user_id)

    # Потрачено
    spent_today = round(today * COST_PER_PUFF, 2)
    spent_month = round(month * COST_PER_PUFF, 2)

    # =========================
    # ИЗМЕНЕНИЕ СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЮ
    # =========================
    # Используем edit_text вместо answer, чтобы обновить старое сообщение
    try:
        await callback.message.edit_text(
            text=(
                f"🚬 Записал\n\n"
                f"📅 Сегодня: {today}\n"
                f"🗓 За месяц: {month}\n\n"
                f"💸 Потрачено сегодня: {spent_today}₽\n"
                f"💰 Потрачено за месяц: {spent_month}₽"
            ),
            reply_markup=main_keyboard()
        )
    except Exception:
        # На случай, если текст и цифры вообще не изменились, Telegram выдаст ошибку.
        # Просто игнорируем её, чтобы бот не падал.
        pass

    # =========================
    # УВЕДОМЛЕНИЕ АДМИНУ (оставляем как есть, это же админу)
    # =========================
    try:
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
    except Exception as e:
        print(f"Не удалось отправить уведомление админу: {e}")

    # Обязательно гасим часики на кнопке
    await callback.answer()


# =========================
# ЕЖЕДНЕВНАЯ СВОДКА
# =========================

async def daily_report_loop():

    while True:

        now = ekb_now()

        # 00:00
        if now.hour == 0 and now.minute == 0:

            users = await get_all_users()

            for user_id in users:

                today = await get_day_count(user_id, 1)
                yesterday = await get_day_count(user_id, 2)

                # Если вчера нет данных
                if yesterday == 0 and today != 0:
                    yesterday = 400

                difference = today - yesterday

                if yesterday == 0:
                    percent = 0
                else:
                    percent = round(
                        (abs(difference) / yesterday) * 100,
                        1
                    )

                # =========================
                # ЛОГИКА
                # =========================

                if difference < 0:

                    result = (
                        f"🔥 На {percent}% "
                        f"меньше затяжек"
                    )

                    photo = "images/win.jpg"

                elif difference > 0:

                    result = (
                        f"⚠️ На {percent}% "
                        f"больше затяжек"
                    )

                    photo = "images/lose.jpg"

                else:

                    result = (
                        "➖ Столько же, сколько вчера"
                    )

                    photo = "images/equal.jpg"

                # =========================
                # ТЕКСТ
                # =========================

                text = (
                    f"📊 Сводка за день\n\n"
                    f"🚬 Сегодня: {today}\n"
                    f"🚬 Вчера: {yesterday}\n\n"
                    f"{result}"
                )

                # =========================
                # ПОЛЬЗОВАТЕЛЬ
                # =========================

                with open(photo, "rb") as img:

                    await bot.send_photo(
                        user_id,
                        photo=img,
                        caption=text
                    )

                # =========================
                # АДМИН
                # =========================

                with open(photo, "rb") as img:

                    await bot.send_photo(
                        OWNER_ID,
                        photo=img,
                        caption=(
                            f"📨 Отчёт пользователя\n\n"
                            f"{text}"
                        )
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

                month = await get_month_count(user_id, 1)

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
        # Даём боту «отдохнуть» перед следующим кругом напоминаний
        await asyncio.sleep(10800) # 3 часа (лучше спать НАЧАЛЕ цикла)

        users = await get_all_users()
        for user_id in users:
            try:
                await bot.send_message(
                    user_id,
                    "⏰ Не забывай отмечать затяжки"
                )
                # Микро-пауза между пользователями, чтобы Telegram не забанил за спам
                await asyncio.sleep(0.05) 
            except Exception as e:
                print(f"Ошибка отправки напоминания пользователю {user_id}: {e}")


# =========================
# НЕДЕЛЬНЫЙ ОТЧЁТ
# =========================

async def get_week_count(user_id, weeks_ago=0):
    now = ekb_now()
    start_of_week = now - timedelta(days=now.weekday())
    target_week_start = start_of_week - timedelta(weeks=weeks_ago)

    total = 0
    async with aiosqlite.connect(DB_NAME) as db:
        for i in range(7):
            day = (target_week_start + timedelta(days=i)).strftime("%Y-%m-%d")
            cursor = await db.execute(
                """
                SELECT COUNT(*)
                FROM smokes
                WHERE user_id = ?
                AND date LIKE ?
                """,
                (user_id, f"{day}%")
            )
            result = await cursor.fetchone()
            total += result[0]
            
    return total


async def weekly_report_loop():
    while True:
        now = ekb_now()

        # Понедельник, 00:00
        if (
            now.weekday() == 0 and
            now.hour == 0 and
            now.minute == 0
        ):
            users = await get_all_users()

            for user_id in users:
                # 1 неделя назад (которая только что закончилась)
                current_week = await get_week_count(user_id, 1)
                # 2 недели назад
                previous_week = await get_week_count(user_id, 2)

                if previous_week == 0:
                    previous_week = BASELINE_WEEKLY_PUFFS # Используем константу из начала кода

                difference = current_week - previous_week

                percent = round((difference / previous_week) * 100, 1)

                if percent < 0:
                    result = f"🔥 На {abs(percent)}% меньше затяжек"
                elif percent > 0:
                    result = f"⚠️ На {percent}% больше затяжек"
                else:
                    result = "➖ Без изменений"

                # Сделали текст более понятным для человека в понедельник утром
                text = (
                    f"📈 Недельная статистика\n\n"
                    f"🚬 Прошедшая неделя: {current_week}\n"
                    f"🚬 Позапрошлая неделя: {previous_week}\n\n"
                    f"{result}"
                )

                try:
                    await bot.send_message(user_id, text)
                    await bot.send_message(
                        OWNER_ID,
                        f"📨 Недельный отчёт\n\n{text}"
                    )
                    await asyncio.sleep(0.05)
                except Exception as e:
                    print(f"Ошибка отправки недельного отчёта: {e}")

            # Защита от повторного срабатывания в ту же минуту
            await asyncio.sleep(60)

        await asyncio.sleep(15)


# =========================
# MAIN
# =========================

async def main():
    await init_db()
    print("Бот запущен")

    # Запускаем фоновые задачи
    asyncio.create_task(daily_report_loop())
    asyncio.create_task(month_report_loop())
    asyncio.create_task(reminder_loop())
    asyncio.create_task(weekly_report_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
