import asyncio
import logging
import random
import requests
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8671740800:AAGx2A5J14nn4r-T7lNypcox_p57IDCtWHg"
CHANNEL_ID = "@gamevista1_bot"
CHECK_INTERVAL_HOURS = 1

FOOTER_TEXT = "\n\n<i>Этот бот создал Эмиль, если хотите предложить улучшения пишите.</i>"
# =============================================

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

sent_deals = set()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
}


def format_time_left(end_time_str):
    """Отсчет времени до окончания раздачи"""
    if not end_time_str:
        return "Время завершения неизвестно"
    try:
        clean_date = end_time_str.replace("Z", "+00:00")
        end_dt = datetime.fromisoformat(clean_date)
        now = datetime.now(timezone.utc)
        diff = end_dt - now
        if diff.total_seconds() <= 0:
            return "Раздача завершена"

        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days} дн.")
        if hours > 0 or days > 0:
            parts.append(f"{hours} час.")
        parts.append(f"{minutes} мин.")
        return " ".join(parts)
    except Exception as e:
        return "Не определено"


def get_epic_free_games():
    """Бесплатные раздачи Epic Games Store"""
    url = "https://www.gamerpower.com/api/giveaways?platform=epic-games-store"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            games = response.json()
            free_games = []
            for game in games[:5]:
                free_games.append({
                    "id": f"epic_{game.get('id')}",
                    "title": game.get("title"),
                    "link": game.get("open_giveaway_url"),
                    "image": game.get("image"),
                    "time_left": format_time_left(game.get("end_date"))
                })
            return free_games
    except Exception as e:
        logging.error(f"Ошибка Epic Games API: {e}")
    return []


def get_steam_kz_specials(count=20):
    """
    Получение НАСТОЯЩИХ региональных цен Steam для Казахстана (KZT).
    Используется официальный API Steam Store с cc=kz.
    """
    url = "https://store.steampowered.com/api/featuredcategories?cc=kz&l=russian"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            specials_items = data.get("specials", {}).get("items", [])
            
            results = []
            for item in specials_items:
                if not item.get("discount_expiration") and item.get("discount_percent", 0) == 0:
                    continue

                appid = item.get("id")
                title = item.get("name")
                discount = item.get("discount_percent", 0)
                
                # Цены в API передаются в тиинах (копейках тенге), делим на 100
                final_price_kzt = item.get("final_price", 0) / 100
                original_price_kzt = item.get("original_price", 0) / 100
                
                link = f"https://store.steampowered.com/app/{appid}/"
                image_url = item.get("large_capsule_image") or item.get("header_image")

                if final_price_kzt == 0:
                    price_str = "<b>БЕСПЛАТНО</b>"
                    normal_price_str = ""
                else:
                    price_str = f"{final_price_kzt:,.0f} ₸".replace(",", " ")
                    normal_price_str = f"{original_price_kzt:,.0f} ₸".replace(",", " ")

                results.append({
                    "id": f"steam_kz_{appid}",
                    "title": title,
                    "savings": discount,
                    "price_kzt": final_price_kzt,
                    "price_str": price_str,
                    "normal_price_str": normal_price_str,
                    "link": link,
                    "image": image_url
                })
            return results[:count]
    except Exception as e:
        logging.error(f"Ошибка получения цен Steam KZ: {e}")
    return []


async def send_photo_or_text(message_or_bot, target_id, photo_url, caption):
    """Отправка фото с подписью"""
    try:
        if isinstance(message_or_bot, Bot):
            await message_or_bot.send_photo(chat_id=target_id, photo=photo_url, caption=caption, disable_web_page_preview=False)
        else:
            await message_or_bot.answer_photo(photo=photo_url, caption=caption, disable_web_page_preview=False)
    except Exception as e:
        logging.warning(f"Не удалось отправить фото, отправка текстом: {e}")
        if isinstance(message_or_bot, Bot):
            await message_or_bot.send_message(chat_id=target_id, text=caption, disable_web_page_preview=False)
        else:
            await message_or_bot.answer(caption, disable_web_page_preview=False)


async def send_deals_job():
    """Автопостинг новых скидок раз в час в канал"""
    epic_games = get_epic_free_games()
    steam_deals = get_steam_kz_specials(count=10)

    # 1. Epic Games
    for game in epic_games:
        if game["id"] not in sent_deals:
            text = (
                f"🎁 <b>БЕСПЛАТНАЯ РАЗДАЧА В EPIC GAMES!</b>\n\n"
                f"🎮 <b><a href='{game['link']}'>{game['title']}</a></b>\n"
                f"💰 Цена: <b>БЕСПЛАТНО</b>\n"
                f"⏳ Осталось до конца: <b>{game['time_left']}</b>"
                f"{FOOTER_TEXT}"
            )
            await send_photo_or_text(bot, CHANNEL_ID, game["image"], text)
            sent_deals.add(game["id"])
            await asyncio.sleep(2)

    # 2. Steam KZ Скидки
    for deal in steam_deals:
        if deal["id"] not in sent_deals:
            if deal["price_kzt"] == 0:
                price_info = "<b>БЕСПЛАТНО</b>"
            else:
                price_info = (
                    f"<s>{deal['normal_price_str']}</s>\n"
                    f"🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)"
                )

            text = (
                f"🏷 <b>НОВАЯ СКИДКА В STEAM (Казахстан 🇰🇿)!</b>\n\n"
                f"🎮 <b><a href='{deal['link']}'>{deal['title']}</a></b>\n"
                f"💰 Цена:\n{price_info}"
                f"{FOOTER_TEXT}"
            )
            await send_photo_or_text(bot, CHANNEL_ID, deal["image"], text)
            sent_deals.add(deal["id"])
            await asyncio.sleep(2)


# ================= СЛОТЫ КОМАНД =================

@dp.message(Command("start"))
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """/help — Список всех команд"""
    text = (
        "🤖 <b>Список всех команд бота GameVista (Регион: Казахстан 🇰🇿):</b>\n\n"
        "🔹 /test — Проверка работоспособности бота\n"
        "🔹 /steam — Случайная скидка из Steam (в ₸)\n"
        "🔹 /steamtop — Скидка на популярную игру в Steam (в ₸)\n"
        "🔹 /steamdeal — Лучшая скидка дня в Steam (в ₸)\n"
        "🔹 /steamearly — Популярные игры со скидкой (в ₸)\n"
        "🔹 /giveaway — Актуальные бесплатные раздачи Epic Games\n"
        "🔹 /help — Показать это меню команд"
        f"{FOOTER_TEXT}"
    )
    await message.answer(text)


@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    await message.answer(f"бот запущен{FOOTER_TEXT}")


@dp.message(Command("steam"))
async def cmd_steam(message: types.Message):
    """/steam — Случайная скидка"""
    deals = get_steam_kz_specials(count=20)
    if not deals:
        await message.answer(f"Не удалось получить скидки Steam. Попробуйте еще раз.{FOOTER_TEXT}")
        return

    deal = random.choice(deals)
    price_info = f"<s>{deal['normal_price_str']}</s>\n🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)" if deal["price_kzt"] > 0 else "<b>БЕСПЛАТНО</b>"
    
    text = (
        f"🎲 <b>Случайная скидка из Steam (Казахстан 🇰🇿):</b>\n\n"
        f"🎮 <b><a href='{deal['link']}'>{deal['title']}</a></b>\n"
        f"💰 Цена:\n{price_info}"
        f"{FOOTER_TEXT}"
    )
    await send_photo_or_text(message, message.chat.id, deal["image"], text)


@dp.message(Command("steamtop"))
async def cmd_steamtop(message: types.Message):
    """/steamtop — Скидка на популярную игру"""
    deals = get_steam_kz_specials(count=20)
    if not deals:
        await message.answer(f"Не удалось получить скидки.{FOOTER_TEXT}")
        return

    deal = random.choice(deals)
    price_info = f"<s>{deal['normal_price_str']}</s>\n🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)" if deal["price_kzt"] > 0 else "<b>БЕСПЛАТНО</b>"

    text = (
        f"🏆 <b>Скидка в Steam (Казахстан 🇰🇿):</b>\n\n"
        f"🎮 <b><a href='{deal['link']}'>{deal['title']}</a></b>\n"
        f"💰 Цена:\n{price_info}"
        f"{FOOTER_TEXT}"
    )
    await send_photo_or_text(message, message.chat.id, deal["image"], text)


@dp.message(Command("steamdeal"))
async def cmd_steamdeal(message: types.Message):
    """/steamdeal — Лучшая скидка дня"""
    deals = get_steam_kz_specials(count=20)
    if not deals:
        await message.answer(f"Не удалось получить скидки.{FOOTER_TEXT}")
        return

    # Сортируем по проценту скидки
    deals_sorted = sorted(deals, key=lambda x: x["savings"], reverse=True)
    deal = deals_sorted[0]
    
    price_info = f"<s>{deal['normal_price_str']}</s>\n🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)" if deal["price_kzt"] > 0 else "<b>БЕСПЛАТНО</b>"

    text = (
        f"🔥 <b>МАКСИМАЛЬНАЯ СКИДКА В STEAM (Казахстан 🇰🇿):</b>\n\n"
        f"🎮 <b><a href='{deal['link']}'>{deal['title']}</a></b>\n"
        f"💰 Цена:\n{price_info}"
        f"{FOOTER_TEXT}"
    )
    await send_photo_or_text(message, message.chat.id, deal["image"], text)


@dp.message(Command("steamearly"))
async def cmd_steamearly(message: types.Message):
    """/steamearly — Подборка скидок"""
    deals = get_steam_kz_specials(count=20)
    if not deals:
        await message.answer(f"Не удалось получить скидки.{FOOTER_TEXT}")
        return

    deal = random.choice(deals)
    price_info = f"<s>{deal['normal_price_str']}</s>\n🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)" if deal["price_kzt"] > 0 else "<b>БЕСПЛАТНО</b>"

    text = (
        f"🛠 <b>Отличная скидка в Steam (Казахстан 🇰🇿):</b>\n\n"
        f"🎮 <b><a href='{deal['link']}'>{deal['title']}</a></b>\n"
        f"💰 Цена:\n{price_info}"
        f"{FOOTER_TEXT}"
    )
    await send_photo_or_text(message, message.chat.id, deal["image"], text)


@dp.message(Command("giveaway"))
async def cmd_giveaway(message: types.Message):
    """/giveaway — Текущие раздачи Epic Games"""
    games = get_epic_free_games()
    if not games:
        await message.answer(f"Сейчас нет активных раздач Epic Games или не удалось их получить.{FOOTER_TEXT}")
        return

    for game in games:
        text = (
            f"🎁 <b>РАЗДАЧА EPIC GAMES:</b>\n\n"
            f"🎮 <b><a href='{game['link']}'>{game['title']}</a></b>\n"
            f"💰 Цена: <b>БЕСПЛАТНО</b>\n"
            f"⏳ До конца осталось: <b>{game['time_left']}</b>"
            f"{FOOTER_TEXT}"
        )
        await send_photo_or_text(message, message.chat.id, game["image"], text)
        await asyncio.sleep(1)


async def main():
    scheduler.add_job(send_deals_job, "interval", hours=CHECK_INTERVAL_HOURS)
    scheduler.start()

    logging.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
        
