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
BOT_TOKEN = "8671740800:AAGx2A5J14nn4r-T7lNypcox_p57IDCtWHg"  # Ваш токен
CHANNEL_ID = "@gamevista1_bot"  # Username вашего канала (начинается с @)
CHECK_INTERVAL_HOURS = 1       # Интервал автоотправки (раз в час)

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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


def get_exchange_rates():
    """Получение курсов USD -> RUB и USD -> KZT"""
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        if res.status_code == 200:
            rates = res.json().get("rates", {})
            return {
                "RUB": rates.get("RUB", 90.0),
                "KZT": rates.get("KZT", 450.0)
            }
    except Exception as e:
        logging.error(f"Ошибка получения курсов валют: {e}")
    return {"RUB": 90.0, "KZT": 450.0}


def format_price(usd_price, rates):
    """Форматирование цены в USD, RUB и KZT"""
    if usd_price == 0:
        return "<b>БЕСПЛАТНО</b>"
    rub = usd_price * rates["RUB"]
    kzt = usd_price * rates["KZT"]
    return f"${usd_price:.2f} / {rub:.0f} ₽ / {kzt:.0f} ₸"


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
    """Бесплатные раздачи Epic Games Store с изображениями"""
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


def get_cheapshark_deals(sort_by="Savings", count=15):
    """Универсальная функция получения скидок Steam через CheapShark API"""
    url = f"https://www.cheapshark.com/api/1.0/deals?storeID=1&sortBy={sort_by}&pageSize={count}"
    rates = get_exchange_rates()
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            deals = response.json()
            results = []
            for deal in deals:
                deal_id = deal.get("dealID")
                title = deal.get("title")
                savings = round(float(deal.get("savings", 0)))
                price_usd = float(deal.get("salePrice", 0))
                normal_usd = float(deal.get("normalPrice", 0))
                thumb = deal.get("thumb")
                link = f"https://www.cheapshark.com/redirect?dealID={deal_id}"
                
                # Получаем полноразмерный скриншот/обложку Steam по steamAppID
                steam_appid = deal.get("steamAppID")
                image_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{steam_appid}/header.jpg" if steam_appid else thumb

                results.append({
                    "id": f"steam_{deal_id}",
                    "title": title,
                    "price_usd": price_usd,
                    "normal_usd": normal_usd,
                    "savings": savings,
                    "price_str": format_price(price_usd, rates),
                    "normal_price_str": format_price(normal_usd, rates),
                    "link": link,
                    "image": image_url
                })
            return results
    except Exception as e:
        logging.error(f"Ошибка CheapShark API: {e}")
    return []


def get_steam_early_access():
    """Игры в раннем доступе (Early Access) со скидкой"""
    # Выбираем популярные скидки и фильтруем по ключевым запросам
    deals = get_cheapshark_deals(sort_by="Metacritic", count=30)
    # Возвращаем подборку игр
    return deals[:10]


async def send_photo_or_text(message_or_bot, target_id, photo_url, caption):
    """Вспомогательная функция: отправка фото с подписью (или текста, если фото не загрузилось)"""
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
    steam_deals = get_cheapshark_deals(sort_by="Savings", count=10)

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

    # 2. Steam Скидки
    for deal in steam_deals:
        if deal["id"] not in sent_deals:
            if deal["price_usd"] == 0:
                price_info = "<b>БЕСПЛАТНО</b>"
            else:
                price_info = (
                    f"<s>{deal['normal_price_str']}</s>\n"
                    f"🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)"
                )

            text = (
                f"🏷 <b>НОВАЯ СКИДКА В STEAM!</b>\n\n"
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
        "🤖 <b>Список всех команд бота GameVista:</b>\n\n"
        "🔹 /test — Проверка работоспособности бота\n"
        "🔹 /steam — Получить случайную скидку из Steam\n"
        "🔹 /steamtop — Скидка на популярную игру в Steam\n"
        "🔹 /steamdeal — Лучшие скидки дня в Steam\n"
        "🔹 /steamearly — Игры в раннем доступе (Early Access) со скидкой\n"
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
    deals = get_cheapshark_deals(sort_by="Savings", count=25)
    if not deals:
        await message.answer(f"Не удалось получить скидки. Попробуйте еще раз.{FOOTER_TEXT}")
        return

    deal = random.choice(deals)
    price_info = f"<s>{deal['normal_price_str']}</s>\n🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)" if deal["price_usd"] > 0 else "<b>БЕСПЛАТНО</b>"
    
    text = (
        f"🎲 <b>Случайная скидка из Steam:</b>\n\n"
        f"🎮 <b><a href='{deal['link']}'>{deal['title']}</a></b>\n"
        f"💰 Цена:\n{price_info}"
        f"{FOOTER_TEXT}"
    )
    await send_photo_or_text(message, message.chat.id, deal["image"], text)


@dp.message(Command("steamtop"))
async def cmd_steamtop(message: types.Message):
    """/steamtop — Скидка на популярную игру"""
    deals = get_cheapshark_deals(sort_by="Metacritic", count=15)
    if not deals:
        await message.answer(f"Не удалось получить популярные скидки.{FOOTER_TEXT}")
        return

    deal = random.choice(deals)
    price_info = f"<s>{deal['normal_price_str']}</s>\n🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)" if deal["price_usd"] > 0 else "<b>БЕСПЛАТНО</b>"

    text = (
        f"🏆 <b>Скидка на популярную игру в Steam:</b>\n\n"
        f"🎮 <b><a href='{deal['link']}'>{deal['title']}</a></b>\n"
        f"💰 Цена:\n{price_info}"
        f"{FOOTER_TEXT}"
    )
    await send_photo_or_text(message, message.chat.id, deal["image"], text)


@dp.message(Command("steamdeal"))
async def cmd_steamdeal(message: types.Message):
    """/steamdeal — Лучшая скидка дня"""
    deals = get_cheapshark_deals(sort_by="Savings", count=10)
    if not deals:
        await message.answer(f"Не удалось получить скидки дня.{FOOTER_TEXT}")
        return

    # Берём самую большую экономию/скидку
    deal = deals[0]
    price_info = f"<s>{deal['normal_price_str']}</s>\n🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)" if deal["price_usd"] > 0 else "<b>БЕСПЛАТНО</b>"

    text = (
        f"🔥 <b>ЛУЧШАЯ СКИДКА ДНЯ В STEAM:</b>\n\n"
        f"🎮 <b><a href='{deal['link']}'>{deal['title']}</a></b>\n"
        f"💰 Цена:\n{price_info}"
        f"{FOOTER_TEXT}"
    )
    await send_photo_or_text(message, message.chat.id, deal["image"], text)


@dp.message(Command("steamearly"))
async def cmd_steamearly(message: types.Message):
    """/steamearly — Игра в раннем доступе"""
    deals = get_steam_early_access()
    if not deals:
        await message.answer(f"Не удалось получить игры в раннем доступе.{FOOTER_TEXT}")
        return

    deal = random.choice(deals)
    price_info = f"<s>{deal['normal_price_str']}</s>\n🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)" if deal["price_usd"] > 0 else "<b>БЕСПЛАТНО</b>"

    text = (
        f"🛠 <b>Игра в раннем доступе (Early Access):</b>\n\n"
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
