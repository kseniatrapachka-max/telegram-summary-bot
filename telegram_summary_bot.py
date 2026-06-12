#!/usr/bin/env python3
"""
Telegram Summary Bot for Ksenia
Parses YouTube transcripts and generates summaries in her voice
"""

import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
from youtube_transcript_api import YouTubeTranscriptApi
import re

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

Ready for presets? Write key insights briefly for:
- 📝 КОРОТКО (1-2 lines per chapter)
- 📖 ПОДРОБНО (full version above)
- 💬 ЦИТАТЫ (quotes + comment)
- 🔧 ЛАЙФХАКИ (actionable tips)
- 💡 ИНСАЙТЫ (for sharing)
"""

# ==================== YOUTUBE - EXTRACT TRANSCRIPT ====================
def extract_youtube_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
        r'youtube\.com\/watch\?.*v=([^&\n?#]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

async def parse_youtube_transcript(url: str) -> str:
    """
    Extract YouTube transcript using youtube-transcript-api
    """
    logger.info(f"Extracting YouTube transcript from: {url}")
    
    try:
        video_id = extract_youtube_id(url)
        if not video_id:
            logger.error(f"Could not extract video ID from: {url}")
            return None
        
        # Try to get transcript in Russian first, then English
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ru'])
        except:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        
        # Combine transcript entries into one text
        content = '\n'.join([entry['text'] for entry in transcript])
        
        logger.info(f"Successfully extracted transcript ({len(content)} chars)")
        return content
        
    except Exception as e:
        logger.error(f"YouTube transcript extraction error: {e}")
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
        "Я парсю YouTube видео и переписываю их в твоём стиле.\n\n"
        "Просто отправь YouTube ссылку:\n"
        "• https://youtu.be/...\n"
        "• https://www.youtube.com/watch?v=...\n\n"
        "Я вытащу транскрипт, переделаю в твоём голосе и отправлю summary."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages"""
    chat_id = update.message.chat_id
    
    try:
        # Check if it's a YouTube URL
        if update.message.text and ("youtube.com" in update.message.text or "youtu.be" in update.message.text):
            url = update.message.text.strip()
            
            # Show typing indicator
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
            
            # Send initial message
            status_msg = await update.message.reply_text("⏳ Вытаскиваю транскрипт YouTube...")
            
            # Extract YouTube transcript
            content = await parse_youtube_transcript(url)
            
            if not content or len(content) < 100:
                await status_msg.edit_text(
                    "❌ Не удалось получить транскрипт.\n\n"
                    "Возможные причины:\n"
                    "• Видео нет с субтитрами\n"
                    "• Неправильная ссылка\n"
                    "• Видео заблокировано\n\n"
                    "Попробуй другое видео."
                )
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
                        await update.message.reply_text(part, reply_markup=reply_markup)
                    else:
                        await update.message.reply_text(part)
            else:
                await update.message.reply_text(summary, reply_markup=reply_markup)
        
        else:
            await update.message.reply_text(
                "Пожалуйста, отправь YouTube ссылку.\n\n"
                "Примеры:\n"
                "• https://youtu.be/abc123\n"
                "• https://www.youtube.com/watch?v=abc123"
            )
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

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
