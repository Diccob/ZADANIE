import asyncio
from datetime import datetime

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

bot = Bot(token=TOKEN)
dp = Dispatcher()


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


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Нажми кнопку если закурил",
        reply_markup=main_keyboard()
    )


async def get_today_count(user_id):
    today = datetime.now().strftime("%Y-%m-%d")

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


async def get_month_count(user_id):
    month = datetime.now().strftime("%Y-%m")

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


@dp.callback_query(F.data == "smoke")
async def smoke(callback: CallbackQuery):

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO smokes (user_id, date)
            VALUES (?, ?)
            """,
            (callback.from_user.id, now)
        )
        await db.commit()

    today = await get_today_count(callback.from_user.id)
    month = await get_month_count(callback.from_user.id)

    await callback.message.edit_text(
        f"🚬 Записал\n\n"
        f"Сегодня: {today}\n"
        f"За месяц: {month}",
        reply_markup=main_keyboard()
    )

    await bot.send_message(
        OWNER_ID,
        f"⚠️ Друг закурил\n\n"
        f"Сегодня: {today}\n"
        f"За месяц: {month}\n"
        f"Время: {datetime.now().strftime('%H:%M')}"
    )

    await callback.answer()


async def main():
    await init_db()
    print("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
