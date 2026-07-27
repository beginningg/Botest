import asyncio
import logging
import random
import requests
import google.generativeai as genai
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8671740800:AAGx2A5J14nn4r-T7lNypcox_p57IDCtWHg"
CHANNEL_ID = "@gamevista1_bot"
CHECK_INTERVAL_HOURS = 1

# Настройка Gemini AI
GEMINI_API_KEY = "AQ.Ab8RN6L9ufvHxoBuIyF5eyCOqbiq-PG3-DO6SZ7pEwmdKtoPkw"
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel("gemini-1.5-flash")

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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}


def get_steam_kz_specials(count=20):
    """
    Получение НАСТОЯЩИХ региональных цен и акций Steam для Казахстана (KZT).
    """
    url = "https://store.steampowered.com/api/featuredcategories?cc=kz&l=russian"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            specials_items = data.get("specials", {}).get("items", [])
            
            results = []
            for item in specials_items:
                discount = item.get("discount_percent", 0)
                final_price_kzt = item.get("final_price", 0) / 100
                original_price_kzt = item.get("original_price", 0) / 100

                # Пропускаем товары без скидки
                if discount == 0 and final_price_kzt > 0:
                    continue

                appid = item.get("id")
                title = item.get("name")
                
                link = f"https://store.steampowered.com/app/{appid}/"
                image_url = item.get("large_capsule_image") or item.get("header_image")

                price_str = f"{final_price_kzt:,.0f} ₸".replace(",", " ") if final_price_kzt > 0 else "<b>БЕСПЛАТНО</b>"
                normal_price_str = f"{original_price_kzt:,.0f} ₸".replace(",", " ") if original_price_kzt > 0 else ""

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
    steam_deals = get_steam_kz_specials(count=15)

    for deal in steam_deals:
        if deal["id"] not in sent_deals:
            price_info = (
                "<b>БЕСПЛАТНО</b>" if deal["price_kzt"] == 0 
                else f"<s>{deal['normal_price_str']}</s>\n🔥 <b>{deal['price_str']}</b> (-{deal['savings']}%)"
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
        "🔹 /steam10 — Топ 10 популярных скидок в Steam\n"
        "🔹 /ai &lt;запрос&gt; — Задать вопрос искусственному интеллекту\n"
        "🔹 /steam — Случайная скидка из Steam (в ₸)\n"
        "🔹 /steamtop — Скидка на популярную игру в Steam (в ₸)\n"
        "🔹 /steamdeal — Лучшая скидка дня в Steam (в ₸)\n"
        "🔹 /steamearly — Подборка отличных скидок (в ₸)\n"
        "🔹 /test — Проверка работоспособности бота\n"
        "🔹 /help — Показать это меню команд"
        f"{FOOTER_TEXT}"
    )
    await message.answer(text)


@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    await message.answer(f"бот запущен{FOOTER_TEXT}")


@dp.message(Command("steam10"))
async def cmd_steam10(message: types.Message):
    """/steam10 — Топ-10 популярных игр со скидками"""
    deals = get_steam_kz_specials(count=10)
    if not deals:
        await message.answer(f"Не удалось получить скидки Steam.{FOOTER_TEXT}")
        return

    text = "🔥 <b>ТОП-10 ПОПУЛЯРНЫХ СКИДОК В STEAM (Казахстан 🇰🇿):</b>\n\n"
    for idx, deal in enumerate(deals, start=1):
        price_str = f"<b>{deal['price_str']}</b> (-{deal['savings']}%)" if deal["price_kzt"] > 0 else "<b>БЕСПЛАТНО</b>"
        text += f"{idx}. <b><a href='{deal['link']}'>{deal['title']}</a></b> — {price_str}\n"

    text += FOOTER_TEXT
    await message.answer(text, disable_web_page_preview=True)


@dp.message(Command("ai"))
async def cmd_ai(message: types.Message, command: CommandObject):
    """/ai — Запрос к ИИ"""
    prompt = command.args
    if not prompt:
        await message.answer(f"Пожалуйста, напишите запрос после команды.\nПример: <code>/ai посоветуй хорошие шутеры</code>{FOOTER_TEXT}")
        return

    wait_msg = await message.answer("🤖 <i>Думаю над ответом...</i>")

    try:
        # Отправляем запрос в модель Gemini
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: ai_model.generate_content(prompt))
        
        reply_text = f"🤖 <b>Ответ ИИ:</b>\n\n{response.text}{FOOTER_TEXT}"
        await wait_msg.edit_text(reply_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logging.error(f"Ошибка ИИ запроса: {e}")
        await wait_msg.edit_text(f"Произошла ошибка при обращении к ИИ: {e}{FOOTER_TEXT}")


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


async def main():
    scheduler.add_job(send_deals_job, "interval", hours=CHECK_INTERVAL_HOURS)
    scheduler.start()

    logging.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
