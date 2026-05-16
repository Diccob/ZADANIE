import random
import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile  # Добавили корректный импорт для работы с файлами в aiogram 3
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
COST_PER_PUFF = round(MONTHLY_COST / PUFFS_PER_MONTH, 4)
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
    target_month = (now.replace(day=1) - timedelta(days=30 * months_ago)).strftime("%Y-%m")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM smokes WHERE user_id = ? AND date LIKE ?",
            (user_id, f"{target_month}%")
        )
        result = await cursor.fetchone()
        return result[0]

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

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT DISTINCT user_id FROM smokes")
        result = await cursor.fetchall()
        return [row[0] for row in result]


# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

    try:
        await message.answer(
            "🚬 Нажми кнопку если затянулся",
            reply_markup=main_keyboard()
        )
    except Exception as e:
        print(f"Ошибка при отправке старта: {e}")


# =========================
# КНОПКА ЗАТЯЖКИ
# =========================

@dp.callback_query(F.data == "smoke")
async def smoke(callback: CallbackQuery):
    try:
        now = ekb_now().strftime("%Y-%m-%d %H:%M:%S")
        user_id = callback.from_user.id
        username = callback.from_user.username
        first_name = callback.from_user.first_name

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO smokes (user_id, date) VALUES (?, ?)",
                (user_id, now)
            )
            await db.commit()

        today = await get_day_count(user_id, 0)
        month = await get_month_count(user_id)

        spent_today = round(today * COST_PER_PUFF, 2)
        spent_month = round(month * COST_PER_PUFF, 2)

        # Базовый текст статистики
        text = (
            f"🚬 Записал\n\n"
            f"📅 Сегодня: {today}\n"
            f"🗓 За месяц: {month}\n\n"
            f"💸 Потрачено сегодня: {spent_today}₽\n"
            f"💰 Потрачено за месяц: {spent_month}₽"
        )

        alert_text = None
        if today == 100:
            alert_text = "🚨 СТОП! Это твоя 100-я затяжка за сегодня! Это очень плохо, тебе нужно сдерживаться!"

        # ПРОВЕРКА НА ЛИМИТ ВАРНИНГА (100+ затяжек)
        if today >= 100:
            text += "\n\n⚠️ <b>ЛИМИТ ПРЕВЫШЕН!</b>\n100+ затяжек за день — это очень плохо. Твоему организму тяжело, постарайся сдерживать себя!"
            
            # Если это ОЖЕ сообщение с фото (101-я затяжка и далее)
            if callback.message.photo:
                try:
                    await callback.message.edit_caption(
                        caption=text,
                        reply_markup=main_keyboard(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Ошибка обновления капшна фото: {e}")
            
            # Если это был ТЕКСТ (ровно 100-я затяжка), переключаемся на режим фото
            else:
                try:
                    photo_file = FSInputFile("images/puff.jpg")
                    # Сначала отправляем КРАСИВОЕ новое сообщение с фото
                    await callback.message.answer_photo(
                        photo=photo_file,
                        caption=text,
                        reply_markup=main_keyboard(),
                        parse_mode="HTML"
                    )
                    # И только если оно отправилось успешно — удаляем старый текст
                    try:
                        await callback.message.delete()
                    except Exception:
                        pass
                except Exception as e:
                    print(f"Не удалось отправить puff.jpg (возможно нет файла): {e}")
                    # Фоллбек: если картинка сломалась/исчезла, просто обновляем старый текст
                    try:
                        await callback.message.edit_text(text, reply_markup=main_keyboard(), parse_mode="HTML")
                    except Exception:
                        pass
        else:
            # ОБЫЧНЫЙ РЕЖИМ (до 100 затяжек)
            try:
                await callback.message.edit_text(text, reply_markup=main_keyboard(), parse_mode="HTML")
            except Exception:
                pass

        # Уведомление админу
        admin_warning_prefix = "🚨" if today >= 100 else "📝"
        try:
            await bot.send_message(
                OWNER_ID,
                f"{admin_warning_prefix} Новая затяжка\n\n"
                f"👤 Пользователь: {first_name}\n"
                f"📎 Username: @{username}\n\n"
                f"🚬 Сегодня: {today} {'(ПРЕВЫШЕНИЕ!)' if today >= 100 else ''}\n"
                f"📅 За месяц: {month}\n"
                f"💸 Сегодня потрачено: {spent_today}₽\n"
                f"⏰ Время: {ekb_now().strftime('%H:%M')}"
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление админу: {e}")

        await callback.answer(text=alert_text, show_alert=True if alert_text else False)

    except Exception as e:
        print(f"Ошибка при обработке затяжки: {e}")


# =========================
# ЕЖЕДНЕВНАЯ СВОДКА
# =========================

async def daily_report_loop():
    while True:
        try:
            now = ekb_now()

            if now.hour == 0 and now.minute == 0:
                users = await get_all_users()

                for user_id in users:
                    try:
                        today = await get_day_count(user_id, 1)
                        yesterday = await get_day_count(user_id, 2)

                        if yesterday == 0 and today != 0:
                            yesterday = 400

                        difference = today - yesterday

                        if yesterday == 0:
                            percent = 0
                        else:
                            percent = round((abs(difference) / yesterday) * 100, 1)

                        if difference < 0:
                            result = f"🔥 На {percent}% меньше затяжек"
                            photo = "images/win.jpg"
                        elif difference > 0:
                            result = f"⚠️ На {percent}% больше затяжек"
                            photo = "images/lose.jpg"
                        else:
                            result = "➖ Столько же, сколько вчера"
                            photo = "images/equal.jpg"

                        text = (
                            f"📊 Сводка за день\n\n"
                            f"🚬 Сегодня: {today}\n"
                            f"🚬 Вчера: {yesterday}\n\n"
                            f"{result}"
                        )

                        # Безопасная отправка через FSInputFile
                        try:
                            photo_file = FSInputFile(photo)
                            await bot.send_photo(user_id, photo=photo_file, caption=text)
                        except Exception:
                            await bot.send_message(user_id, text)

                        try:
                            photo_file = FSInputFile(photo)
                            await bot.send_photo(OWNER_ID, photo=photo_file, caption=f"📨 Отчёт пользователя\n\n{text}")
                        except Exception:
                            await bot.send_message(OWNER_ID, f"📨 Отчёт пользователя\n\n{text}")

                        await asyncio.sleep(0.05)

                    except Exception as user_err:
                        print(f"Ошибка дневного отчета для {user_id}: {user_err}")

                await asyncio.sleep(60)

        except Exception as global_err:
            print(f"Глобальная ошибка в daily_report_loop: {global_err}")
            
        await asyncio.sleep(15)


# =========================
# МЕСЯЧНАЯ СВОДКА
# =========================

async def month_report_loop():
    while True:
        try:
            now = ekb_now()

            if now.day == 1 and now.hour == 0 and now.minute == 0:
                users = await get_all_users()

                for user_id in users:
                    try:
                        month = await get_month_count(user_id, 1)
                        text = (
                            f"📅 Сводка за месяц\n\n"
                            f"🚬 Всего затяжек: {month}\n"
                            f"💸 Потрачено: {MONTHLY_COST}₽"
                        )
                        await bot.send_message(user_id, text)
                        await bot.send_message(OWNER_ID, f"📨 Месячный отчёт\n\n{text}")
                        await asyncio.sleep(0.05)
                    except Exception as user_err:
                        print(f"Ошибка месячного отчета для {user_id}: {user_err}")

                await asyncio.sleep(60)

        except Exception as global_err:
            print(f"Глобальная ошибка в month_report_loop: {global_err}")
            
        await asyncio.sleep(15)


# =========================
# НЕДЕЛЬНЫЙ ОТЧЁТ
# =========================

async def weekly_report_loop():
    while True:
        try:
            now = ekb_now()

            if now.weekday() == 0 and now.hour == 0 and now.minute == 0:
                users = await get_all_users()

                for user_id in users:
                    try:
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

                        text = (
                            f"📈 Недельная статистика\n\n"
                            f"🚬 Прошедшая неделя: {current_week}\n"
                            f"🚬 Позапрошлая неделя: {previous_week}\n\n"
                            f"{result}"
                        )

                        await bot.send_message(user_id, text)
                        await bot.send_message(OWNER_ID, f"📨 Недельный отчёт\n\n{text}")
                        await asyncio.sleep(0.05)
                    except Exception as e:
                        print(f"Ошибка недельного отчета для {user_id}: {e}")

                await asyncio.sleep(60)

        except Exception as global_err:
            print(f"Глобальная ошибка в weekly_report_loop: {global_err}")

        await asyncio.sleep(15)


# =========================
# НАПОМИНАНИЯ
# =========================

async def reminder_loop():
    while True:
        try:
            await asyncio.sleep(10800) # 3 часа
            
            users = await get_all_users()
            for user_id in users:
                try:
                    await bot.send_message(user_id, "⏰ Не забывай отмечать затяжки")
                    await asyncio.sleep(0.05) 
                except Exception as e:
                    print(f"Ошибка напоминания для {user_id}: {e}")
        except Exception as global_err:
            print(f"Глобальная ошибка в reminder_loop: {global_err}")


# =========================
# MAIN
# =========================

async def main():
    try:
        await init_db()
        print("База данных подключена. Бот запускается...")

        asyncio.create_task(daily_report_loop())
        asyncio.create_task(month_report_loop())
        asyncio.create_task(reminder_loop())
        asyncio.create_task(weekly_report_loop())

        await bot.delete_webhook()
        print("Бот успешно запущен и готов к работе!")

        await dp.start_polling(bot)

    except Exception as e:
        print(f"Критическая ошибка запуска: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен вручную.")
