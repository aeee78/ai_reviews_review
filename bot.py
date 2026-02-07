import asyncio
import os
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from dotenv import load_dotenv

# Импортируем наши модули
from parser import parse_ozon_reviews
from gemini_ai import summarize_reviews

load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()


# --- ФУНКЦИЯ ДЛЯ ИСПРАВЛЕНИЯ MARKDOWN ---
def fix_markdown(text):
    """
    Исправляет типичные проблемы Markdown для Telegram.
    """
    # Заменяем ** на * (Telegram использует одинарные для bold)
    text = text.replace("**", "*")
    
    # Убираем тройные ``` если есть (code blocks)
    text = re.sub(r'```\w*\n?', '', text)
    
    # Проверяем парность символов * и _
    # Если нечетное количество - убираем последний
    for char in ['*', '_', '`']:
        count = text.count(char)
        if count % 2 != 0:
            # Находим последний и убираем
            last_pos = text.rfind(char)
            text = text[:last_pos] + text[last_pos + 1:]
    
    return text


def escape_markdown(text):
    """
    Экранирует спецсимволы для MarkdownV2.
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


# --- ФУНКЦИЯ РАЗБИВКИ ТЕКСТА ---
def smart_split(text, max_length=4000):
    """
    Разбивает текст на части, не превышающие max_length.
    Старается резать по переносам строк (\n), чтобы не рвать смысл.
    """
    if len(text) <= max_length:
        return [text]

    parts = []
    while len(text) > max_length:
        # Ищем ближайший перенос строки перед лимитом
        split_index = text.rfind("\n", 0, max_length)

        if split_index == -1:
            # Если переносов нет (один сплошной текст), режем жестко
            split_index = max_length

        parts.append(text[:split_index])
        text = text[
            split_index:
        ].lstrip()  # Убираем пробелы в начале следующего куска

    if text:
        parts.append(text)

    return parts


async def send_formatted_message(message: Message, text: str, status_msg=None, is_first=False):
    """
    Отправляет сообщение с попыткой Markdown, затем без форматирования.
    """
    # Сначала пробуем исправленный Markdown
    fixed_text = fix_markdown(text)
    
    try:
        if is_first and status_msg:
            await status_msg.edit_text(fixed_text, parse_mode="Markdown")
        else:
            await message.answer(fixed_text, parse_mode="Markdown")
        return True
    except TelegramBadRequest:
        pass
    
    # Если не получилось - отправляем без форматирования
    try:
        # Убираем все Markdown символы для чистого текста
        clean_text = text.replace("*", "").replace("_", "").replace("`", "")
        if is_first and status_msg:
            await status_msg.edit_text(clean_text)
        else:
            await message.answer(clean_text)
        return True
    except Exception as e:
        await message.answer(f"Ошибка отправки: {e}")
        return False


@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "👋 Привет! Я *Ozon AI Summary Bot*.\n\n"
        "Скинь мне ссылку на товар, и я проанализирую отзывы через Gemini.",
        parse_mode="Markdown"
    )


@dp.message(F.text.contains("ozon.ru"))
async def process_link(message: Message):
    url = message.text.strip()
    status_msg = await message.answer(
        "🕵️‍♂️ Запускаю браузер и собираю отзывы (это может занять время)..."
    )

    # 1. Парсинг
    reviews = await parse_ozon_reviews(url, max_reviews=100, max_negative=50)

    if not reviews:
        await status_msg.edit_text(
            "❌ Не удалось собрать отзывы. Проверь ссылку или попробуй позже."
        )
        return

    await status_msg.edit_text(
        f"✅ Собрано {len(reviews)} отзывов.\n🧠 Gemini анализирует..."
    )

    # 2. Анализ ИИ
    summary = await summarize_reviews(reviews)

    # 3. Отправка длинного сообщения частями
    parts = smart_split(summary)

    for i, part in enumerate(parts):
        await send_formatted_message(
            message, 
            part, 
            status_msg=status_msg, 
            is_first=(i == 0)
        )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
