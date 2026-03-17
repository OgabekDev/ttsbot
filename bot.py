"""
Telegram Vocabulary TTS Bot
============================
Processes lines in the format "english_word — translation",
extracts the English word, and replies with its MP3 voice message
via Google Text-to-Speech (gTTS).

Deployed on PythonAnywhere via Flask webhook (see flask_app.py).

Dependencies:
    pip install python-telegram-bot gTTS flask

Environment variables:
    BOT_TOKEN  — your token from @BotFather
"""

import asyncio
import logging
import os
import tempfile

from gtts import gTTS
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Set the BOT_TOKEN environment variable on your server.
BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")

# gTTS language / accent settings.
# tld options: "com" (US), "co.uk" (British), "com.au" (Australian)
TTS_LANG: str = "en"
TTS_TLD: str = "com"

# Accepted separators, tried in order. Em-dash, en-dash, then plain hyphen.
SEPARATORS: list[str] = [" — ", "—", " – ", "–", " - ", "-"]

# Delay (seconds) between audio messages when processing large batches.
BATCH_DELAY: float = 1.0

# Minimum number of words in a batch before the delay kicks in.
BATCH_DELAY_THRESHOLD: int = 5

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_vocabulary_line(line: str) -> str | None:
    """
    Parse a single vocabulary line and return the English word/phrase.

    Accepted formats:
        "english_word — translation"   (em-dash)
        "english_word - translation"   (hyphen)
        "english_word—translation"     (em-dash, no spaces)
        "english_word-translation"     (hyphen, no spaces)

    Returns None for headers, empty lines, or lines without any separator.
    """
    line = line.strip()
    if not line:
        return None

    for sep in SEPARATORS:
        if sep in line:
            english_part = line.split(sep, maxsplit=1)[0].strip()
            return english_part if english_part else None

    return None


async def generate_and_send_audio(
    update: Update,
    english_word: str,
) -> None:
    """
    Generate an MP3 voice message for *english_word* via Google TTS
    and send it as a voice reply.
    The temporary file is always cleaned up afterwards.
    """
    tmp_path: str | None = None
    try:
        tts = gTTS(text=english_word, lang=TTS_LANG, tld=TTS_TLD)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        tts.save(tmp_path)

        logger.info("Generated TTS for %r → %s", english_word, tmp_path)

        with open(tmp_path, "rb") as audio_file:
            await update.message.reply_voice(
                voice=audio_file,
                caption=f"🔊 *{english_word}*",
                parse_mode="Markdown",
            )

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to process %r: %s", english_word, exc)
        await update.message.reply_text(
            f"⚠️ Could not generate audio for *{english_word}*.",
            parse_mode="Markdown",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.debug("Deleted temp file: %s", tmp_path)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — send a welcome message explaining the expected input format."""
    welcome = (
        "👋 Hello! I'm your Vocabulary Pronunciation Bot.\n\n"
        "Send me a list of words (one per line, like *'banana — banan'*), "
        "and I'll send audio for the English parts!"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")
    logger.info("User %s started the bot.", update.effective_user.id)


async def vocabulary_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle any plain-text message.

    1. Split the message by newlines.
    2. Parse each line; skip invalid/empty ones.
    3. For each valid English word, generate and send TTS audio.
    4. Apply a short delay between items when the batch is large.
    """
    text: str = update.message.text or ""
    lines = text.splitlines()

    words = [w for line in lines if (w := parse_vocabulary_line(line))]

    if not words:
        await update.message.reply_text(
            "🤔 Hech qanday to'g'ri so'z topilmadi.\n"
            "Iltimos, quyidagi formatda yozing: *so'z — tarjima*",
            parse_mode="Markdown",
        )
        return

    logger.info(
        "Processing %d word(s) for user %s.", len(words), update.effective_user.id
    )

    use_delay = len(words) >= BATCH_DELAY_THRESHOLD

    for index, word in enumerate(words):
        await generate_and_send_audio(update, word)

        if use_delay and index < len(words) - 1:
            await asyncio.sleep(BATCH_DELAY)


# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------

def get_application() -> Application:
    """Build the application object without starting it."""
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not set. Add it to your WSGI file or environment."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, vocabulary_handler)
    )
    return app


async def main() -> None:
    """Build and run the bot using long-polling (for local testing)."""
    app = get_application()
    
    logger.info("Bot is running via long-polling (local dev mode).")

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        # Keep running until the process is stopped.
        await asyncio.Event().wait()

        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
