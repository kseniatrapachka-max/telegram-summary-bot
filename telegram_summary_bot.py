#!/usr/bin/env python3
"""
Telegram Summary Bot for Ksenia
Supadata for YouTube transcripts + Gemini for voice rewrite
"""

import logging
import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction

# ==================== CONFIGURATION ====================
TELEGRAM_TOKEN = "8849119684:AAGxdB3cehF_8SL1s9_1sCX2ZgBwv0fOJlA"
SUPADATA_KEY = "sd_f36335dc0ed52aa9cd950726878096ef"
GEMINI_KEY = "AQ.Ab8RN6K_-ioT7GjxocxmqW6Kwwp9Zv7Jm-HVG1hmB5sr8rfX0w"

SUPADATA_URL = "https://api.supadata.ai/v1/youtube/transcript"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== KSENIA'S VOICE PROMPT ====================
SYSTEM_PROMPT = """Ты создаёшь саммари для Ксении, 24-летнего арт-директора в Варшаве.

ЕЁ ГОЛОС:
- Умный, ироничный русскоязычный друг. Прямой, честный.
- Никакого корпоративного тона, никаких оговорок, никакого филлера.
- Использует: типа, короче, рил, реально, жиза, вайб, прям, если честно
- Переключается русский + польский (plis, spoki) + английский естественно
- Короткие предложения после длинных (ритм)
- Обращение на ты, конкретные примеры, никаких очевидных утверждений
- Без тире, без "не только X но и Y"
- Заканчивает на самой сильной мысли, не на резюме

КОНТЕНТ ДЛЯ САММАРИ:
{content}

ЗАДАЧА:
1. Разбей на 4-6 глав максимум
2. Для каждой главы: хук → основная идея → конкретный пример → почему это важно
3. Перепиши в её голосе (умный друг, не учебник)
4. Добавь теги: 🔧 ЛАЙФХАК / 💬 ЦИТАТА / 📊 ФАКТ / 💡 ИНСАЙТ / 🎯 ДЛЯ ТЕБЯ
5. Каждая глава заканчивается на сильной мысли, без резюме
6. Пиши на РУССКОМ

ФОРМАТ:
📺 [Название видео]

---

ГЛАВА 1: [Название]
[Саммари в голосе Ксении, макс 3 предложения на абзац]
[Теги]

---

ГЛАВА 2: [Название]
...
"""

# ==================== SUPADATA ====================
def extract_youtube_id(url: str) -> str:
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
        r'youtube\.com\/watch\?.*v=([^&\n?#]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

async def get_transcript(url: str) -> str:
    logger.info(f"Getting transcript: {url}")
    try:
        video_id = extract_youtube_id(url)
        if not video_id:
            return None

        r = requests.get(
            SUPADATA_URL,
            params={"videoId": video_id, "lang": "en", "text": "true"},
            headers={"x-api-key": SUPADATA_KEY},
            timeout=30
        )
        logger.info(f"Supadata: {r.status_code} {r.text[:300]}")

        if r.status_code == 200:
            data = r.json()
            content = data.get("content") or data.get("transcript") or data.get("text")
            if content:
                if isinstance(content, list):
                    content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                return content
        return None
    except Exception as e:
        logger.error(f"Supadata error: {e}")
        return None

# ==================== GEMINI ====================
async def rewrite_with_gemini(content: str) -> str:
    logger.info(f"Rewriting with Gemini ({len(content)} chars)")
    
    if len(content) > 8000:
        content = content[:8000] + "..."

    prompt = SYSTEM_PROMPT.format(content=content)

    try:
        r = requests.post(
            GEMINI_URL,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            headers={"Content-Type": "application/json"},
            timeout=120
        )
        logger.info(f"Gemini: {r.status_code} {r.text[:200]}")
        r.raise_for_status()

        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None

# ==================== HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Отправь YouTube ссылку — сделаю саммари в твоём стиле.\n\n"
        "• https://youtu.be/...\n"
        "• https://www.youtube.com/watch?v=..."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    text = update.message.text or ""

    try:
        if "youtube.com" in text or "youtu.be" in text:
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
            status = await update.message.reply_text("⏳ Вытаскиваю транскрипт...")

            content = await get_transcript(text.strip())

            if not content or len(content) < 50:
                await status.edit_text(
                    "❌ Нет транскрипта.\n\n"
                    "Видео без субтитров или закрытое.\n"
                    "Попробуй другое видео."
                )
                return

            await status.edit_text("⏳ Переписываю в твоём стиле...")

            summary = await rewrite_with_gemini(content)

            if not summary:
                await status.edit_text("❌ Ошибка Gemini. Попробуй снова.")
                return

            await status.delete()

            keyboard = [
                [
                    InlineKeyboardButton("📝 КОРОТКО", callback_data="short"),
                    InlineKeyboardButton("📖 ПОДРОБНО", callback_data="full")
                ],
                [
                    InlineKeyboardButton("💬 ЦИТАТЫ", callback_data="quotes"),
                    InlineKeyboardButton("🔧 ЛАЙФХАКИ", callback_data="hacks")
                ],
                [InlineKeyboardButton("💡 ИНСАЙТЫ", callback_data="insights")]
            ]

            if len(summary) > 4000:
                parts = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
                for i, part in enumerate(parts):
                    markup = InlineKeyboardMarkup(keyboard) if i == len(parts) - 1 else None
                    await update.message.reply_text(part, reply_markup=markup)
            else:
                await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))

        else:
            await update.message.reply_text(
                "Отправь YouTube ссылку:\n"
                "• https://youtu.be/...\n"
                "• https://www.youtube.com/watch?v=..."
            )

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:150]}")

async def preset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    names = {"short": "📝 КОРОТКО", "full": "📖 ПОДРОБНО", "quotes": "💬 ЦИТАТЫ", "hacks": "🔧 ЛАЙФХАКИ", "insights": "💡 ИНСАЙТЫ"}
    await query.edit_message_text(f"{names.get(query.data, query.data)} — скоро будет 🚀")

# ==================== MAIN ====================
def main():
    logger.info("Starting bot...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(CallbackQueryHandler(preset_handler))
    app.run_polling()

if __name__ == "__main__":
    main()

