#!/usr/bin/env python3
"""
Telegram Summary Bot for Ksenia
Uses Supadata API for YouTube transcripts + OpenRouter for voice rewrite
"""

import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
import re

# ==================== CONFIGURATION ====================
OPENROUTER_KEY = "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"
TELEGRAM_TOKEN = "8849119684:AAGxdB3cehF_8SL1s9_1sCX2ZgBwv0fOJlA"
SUPADATA_KEY = "sd_f36335dc0ed52aa9cd950726878096ef"

OPENROUTER_URL = "https://api.openrouter.ai/api/v1/messages"
SUPADATA_URL = "https://api.supadata.ai/v1/youtube/transcript"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== KSENIA'S VOICE PROMPT ====================
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

CONTENT TO SUMMARIZE:
{content}

TASK:
1. Break into 4-6 chapters (max)
2. For each chapter: hook → core idea → concrete example → why it matters
3. Rewrite in her voice (smart friend, not textbook)
4. Add tags: 🔧 ЛАЙФХАК / 💬 ЦИТАТА / 📊 ФАКТ / 💡 ИНСАЙТ / 🎯 ДЛЯ ТЕБЯ
5. End each chapter on strongest thought, no summary
6. Write in RUSSIAN

OUTPUT FORMAT:
📺 [Title]

---

ГЛАВА 1: [Title]
[Summary in Ksenia's voice]
[Tags]

---

ГЛАВА 2: [Title]
...
"""

# ==================== SUPADATA - YOUTUBE TRANSCRIPT ====================
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

async def get_youtube_transcript(url: str) -> str:
    logger.info(f"Getting transcript via Supadata: {url}")
    
    try:
        video_id = extract_youtube_id(url)
        if not video_id:
            return None

        response = requests.get(
            SUPADATA_URL,
            params={"videoId": video_id, "lang": "en", "text": "true"},
            headers={"x-api-key": SUPADATA_KEY},
            timeout=30
        )
        
        logger.info(f"Supadata response: {response.status_code} - {response.text[:200]}")
        
        if response.status_code == 200:
            data = response.json()
            # Supadata returns content field with the transcript text
            content = data.get("content") or data.get("transcript") or data.get("text")
            if content:
                if isinstance(content, list):
                    content = " ".join([c.get("text", "") for c in content])
                logger.info(f"Got transcript: {len(content)} chars")
                return content
        
        logger.error(f"Supadata error: {response.status_code} {response.text}")
        return None
        
    except Exception as e:
        logger.error(f"Supadata exception: {e}")
        return None

# ==================== OPENROUTER - REWRITE ====================
async def rewrite_in_ksenia_voice(content: str) -> str:
    logger.info(f"Rewriting {len(content)} chars")
    
    # Trim content if too long
    if len(content) > 8000:
        content = content[:8000] + "..."
    
    payload = {
        "model": "qwen/qwen-3-235b-a22b:free",
        "messages": [{"role": "user", "content": KSENIA_VOICE_PROMPT.format(content=content)}],
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
            return data["choices"][0]["message"]["content"]
        
        logger.error(f"No choices: {data}")
        return None
        
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        return None

# ==================== TELEGRAM HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Отправь YouTube ссылку — я вытащу транскрипт и перепишу в твоём стиле.\n\n"
        "• https://youtu.be/...\n"
        "• https://www.youtube.com/watch?v=..."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    
    try:
        text = update.message.text or ""
        
        if "youtube.com" in text or "youtu.be" in text:
            url = text.strip()
            
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
            status_msg = await update.message.reply_text("⏳ Вытаскиваю транскрипт...")
            
            content = await get_youtube_transcript(url)
            
            if not content or len(content) < 50:
                await status_msg.edit_text(
                    "❌ Не удалось получить транскрипт.\n\n"
                    "Возможные причины:\n"
                    "• Видео без субтитров\n"
                    "• Видео закрытое или удалённое\n\n"
                    "Попробуй другое видео."
                )
                return
            
            await status_msg.edit_text("⏳ Переписываю в твоём стиле...")
            
            summary = await rewrite_in_ksenia_voice(content)
            
            if not summary:
                await status_msg.edit_text("❌ Ошибка при переписывании. Попробуй снова.")
                return
            
            await status_msg.delete()
            
            keyboard = [
                [
                    InlineKeyboardButton("📝 КОРОТКО", callback_data="preset_short"),
                    InlineKeyboardButton("📖 ПОДРОБНО", callback_data="preset_full")
                ],
                [
                    InlineKeyboardButton("💬 ЦИТАТЫ", callback_data="preset_quotes"),
                    InlineKeyboardButton("🔧 ЛАЙФХАКИ", callback_data="preset_hacks")
                ],
                [InlineKeyboardButton("💡 ИНСАЙТЫ", callback_data="preset_insights")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
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
                "Отправь YouTube ссылку:\n"
                "• https://youtu.be/...\n"
                "• https://www.youtube.com/watch?v=..."
            )
    
    except Exception as e:
        logger.error(f"Handler error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:150]}")

async def preset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    preset_names = {
        "preset_short": "📝 КОРОТКО",
        "preset_full": "📖 ПОДРОБНО",
        "preset_quotes": "💬 ЦИТАТЫ",
        "preset_hacks": "🔧 ЛАЙФХАКИ",
        "preset_insights": "💡 ИНСАЙТЫ"
    }
    await query.edit_message_text(
        f"{preset_names.get(query.data, query.data)} — выбрано!\n\nФункция в разработке 🚀"
    )

# ==================== MAIN ====================
def main():
    logger.info("Starting bot...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(CallbackQueryHandler(preset_handler))
    logger.info("Bot polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
