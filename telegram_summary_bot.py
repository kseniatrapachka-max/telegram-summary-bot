#!/usr/bin/env python3
"""
Telegram Summary Bot for Ksenia
Parses YouTube/PDF content and generates summaries in her voice using OpenRouter + Gemini
"""

import os
import json
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
import logging

# ==================== CONFIGURATION ====================
OPENROUTER_KEY = "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"
TELEGRAM_TOKEN = "8849119684:AAGxdB3cehF_8SL1s9_1sCX2ZgBwv0fOJlA"
GEMINI_KEY = "AQ.Ab8RN6K_-ioT7GjxocxmqW6Kwwp9Zv7Jm-HVG1hmB5sr8rfX0w"

OPENROUTER_URL = "https://api.openrouter.ai/api/v1/messages"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== KSENIA'S VOICE SYSTEM PROMPT ====================
KSENIA_VOICE_PROMPT = """You are creating summaries for Ksenia, a 24-year-old art director in Warsaw.

HER VOICE:
- Smart, ironic Russian-speaking friend. Direct, honest.
- No corporate tone, no hedging, no filler.
- Uses: типа, короче, рил, реально, жиза, вайб, прям, если честно
- Code-switches Russian + Polish (plis, spoki, chekni) + English naturally
- Short sentences after long ones (rhythm)
- Personal address (ты), concrete examples, no obvious statements
- No em-dashes, no "not only X but also Y"
- Ends on strongest insight, not summary

HER READING TRIGGERS:
- First sentence: hook that creates tension or names exact pain
- Specific numbers, unusual facts
- Feels personal to HER (design, AI, creativity, career, psychology)
- Visual rhythm: short-long-short sentences
- Each paragraph max 3 sentences
- No corporate language (синергия, инновационный, трансформативный, ключевой)

CONTENT TO SUMMARIZE:
{content}

TASK:
1. Break into 4-6 chapters (max)
2. For each chapter: hook → core idea → concrete example → why it matters to HER
3. Rewrite in her EXACT voice (smart friend, not textbook)
4. Add tags: 🔧 ЛАЙФХАК / 💬 ЦИТАТА / 📊 ФАКТ / 💡 ИНСАЙТ / 🎯 ДЛЯ ТЕБЯ
5. End each chapter on strongest thought (NO summary)
6. Format as Telegram message (clear, readable)

OUTPUT FORMAT:
📺 [Title]
⏱️ [Duration/Length if applicable]

---

CHAPTER 1: [Title]
[Summary in Ksenia's voice, max 3 sentences per paragraph]
[Tags]

---

CHAPTER 2: [Title]
...

---

Готова к пресетам? Напиши:
- 📝 КОРОТКО (1-2 строки на главу)
- 📖 ПОДРОБНО (полная версия выше)
- 💬 ЦИТАТЫ (цитаты + комментарий)
- 🔧 ЛАЙФХАКИ (что применить)
- 💡 ИНСАЙТЫ (для команды/друзей)
"""

# ==================== GEMINI - PARSE CONTENT ====================
async def parse_content(url: str) -> str:
    """
    Parse YouTube video transcript or PDF/article content using Gemini
    """
    logger.info(f"Parsing content from: {url}")
    
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"Extract and return the full transcript or text content from this URL in plain text format, organized by sections/chapters: {url}"
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post(
            GEMINI_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        if "candidates" in data and len(data["candidates"]) > 0:
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            logger.info(f"Successfully parsed content ({len(content)} chars)")
            return content
        else:
            logger.error(f"No content in Gemini response: {data}")
            return None
            
    except Exception as e:
        logger.error(f"Gemini parsing error: {e}")
        return None

# ==================== OPENROUTER - REWRITE IN KSENIA'S VOICE ====================
async def rewrite_in_ksenia_voice(content: str) -> str:
    """
    Rewrite content in Ksenia's voice using OpenRouter
    """
    logger.info(f"Rewriting content in Ksenia's voice ({len(content)} chars)")
    
    full_prompt = KSENIA_VOICE_PROMPT.format(content=content)
    
    payload = {
        "model": "qwen/qwen-3-235b-a22b",
        "messages": [
            {
                "role": "user",
                "content": full_prompt
            }
        ],
        "max_tokens": 3000
    }
    
    try:
        response = requests.post(
            OPENROUTER_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json"
            },
            timeout=120
        )
        response.raise_for_status()
        
        data = response.json()
        if "choices" in data and len(data["choices"]) > 0:
            summary = data["choices"][0]["message"]["content"]
            logger.info(f"Successfully rewrote content")
            return summary
        else:
            logger.error(f"No choices in OpenRouter response: {data}")
            return None
            
    except Exception as e:
        logger.error(f"OpenRouter rewrite error: {e}")
        return None

# ==================== TELEGRAM BOT HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command"""
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я парсю YouTube видео, PDF и статьи, потом переписываю их в твоём стиле.\n\n"
        "Просто отправь:\n"
        "• YouTube ссылку\n"
        "• PDF файл\n"
        "• Текстовый документ\n\n"
        "Я сделаю summary в твоём голосе и спрошу какой формат нужен."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and files"""
    chat_id = update.message.chat_id
    
    try:
        # Check if it's a URL
        if update.message.text and ("youtube.com" in update.message.text or "youtu.be" in update.message.text or "http" in update.message.text):
            url = update.message.text.strip()
            
            # Show typing indicator
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
            
            # Send initial message
            status_msg = await update.message.reply_text("⏳ Парсю контент...")
            
            # Parse content
            content = await parse_content(url)
            
            if not content:
                await status_msg.edit_text("❌ Не удалось распарсить контент. Проверь ссылку и попробуй снова.")
                return
            
            # Update status
            await status_msg.edit_text("⏳ Переписываю в твоём стиле...")
            
            # Rewrite in Ksenia's voice
            summary = await rewrite_in_ksenia_voice(content)
            
            if not summary:
                await status_msg.edit_text("❌ Ошибка при переписывании. Попробуй снова.")
                return
            
            # Delete status message
            await status_msg.delete()
            
            # Send summary with preset buttons
            keyboard = [
                [
                    InlineKeyboardButton("📝 КОРОТКО", callback_data="preset_short"),
                    InlineKeyboardButton("📖 ПОДРОБНО", callback_data="preset_full")
                ],
                [
                    InlineKeyboardButton("💬 ЦИТАТЫ", callback_data="preset_quotes"),
                    InlineKeyboardButton("🔧 ЛАЙФХАКИ", callback_data="preset_hacks")
                ],
                [
                    InlineKeyboardButton("💡 ИНСАЙТЫ", callback_data="preset_insights")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Split message if too long (Telegram limit is 4096 chars)
            if len(summary) > 4000:
                parts = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        # Add buttons only to last part
                        await update.message.reply_text(part, reply_markup=reply_markup)
                    else:
                        await update.message.reply_text(part)
            else:
                await update.message.reply_text(summary, reply_markup=reply_markup)
        
        else:
            await update.message.reply_text(
                "Пожалуйста, отправь YouTube ссылку или текст для анализа.\n\n"
                "Примеры:\n"
                "• https://youtu.be/...\n"
                "• https://www.youtube.com/watch?v=..."
            )
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def preset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle preset button clicks"""
    query = update.callback_query
    await query.answer()
    
    preset = query.data
    preset_names = {
        "preset_short": "📝 КОРОТКО",
        "preset_full": "📖 ПОДРОБНО",
        "preset_quotes": "💬 ЦИТАТЫ",
        "preset_hacks": "🔧 ЛАЙФХАКИ",
        "preset_insights": "💡 ИНСАЙТЫ"
    }
    
    await query.edit_message_text(
        text=f"{preset_names.get(preset, preset)} - выбрано!\n\n"
        f"Функция ещё в разработке. Обновление скоро! 🚀"
    )

# ==================== MAIN ====================
def main():
    """Start the bot"""
    logger.info("Starting Telegram Summary Bot...")
    
    # Create application
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(CallbackQueryHandler(preset_handler))
    
    logger.info("Bot started. Polling for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()
