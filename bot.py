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
import hashlib
import logging
import os
import tempfile
import time

from gtts import gTTS
from gtts.tts import gTTSError
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

# On PythonAnywhere, gTTS can get rate-limited (HTTP 429) because the public IP
# is shared. We mitigate via caching + throttling + retries.
TTS_CACHE_DIR: str = os.environ.get(
    "TTS_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tts_cache"),
)
TTS_MIN_INTERVAL_SECONDS: float = float(os.environ.get("TTS_MIN_INTERVAL_SECONDS", "1.2"))
TTS_MAX_RETRIES: int = int(os.environ.get("TTS_MAX_RETRIES", "3"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_tts_lock = asyncio.Lock()
_last_tts_at: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache_key(text: str) -> str:
    payload = f"{TTS_LANG}|{TTS_TLD}|{text}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload).hexdigest()


def _cache_mp3_path(text: str) -> str:
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)
    return os.path.join(TTS_CACHE_DIR, f"{_cache_key(text)}.mp3")


def _is_probable_429(exc: Exception) -> bool:
    msg = str(exc)
    return "429" in msg or "Too Many Requests" in msg


async def _throttle_tts() -> None:
    global _last_tts_at
    async with _tts_lock:
        now = time.monotonic()
        wait_for = (_last_tts_at + TTS_MIN_INTERVAL_SECONDS) - now
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        _last_tts_at = time.monotonic()


def parse_vocabulary_line(line: str) -> str | None:
    """
    Parse a single vocabulary line and return the English word/phrase.

    Accepted formats (with or without bullet markers like *, •, 1.):
        "english_word — translation"   (em-dash)
        "english_word – translation"   (en-dash)
        "english_word - translation"   (hyphen)
        "english_word"                 (single word, no separator)

    Returns None for empty lines.
    """
    import re

    line = line.strip()
    if not line:
        return None

    # Remove leading bullet markers: *, •, -, or numbered prefixes like "1."
    line = re.sub(r"^(?:[*•]\s+|\d+\.\s+)", "", line).strip()
    if not line:
        return None

    for sep in SEPARATORS:
        if sep in line:
            english_part = line.split(sep, maxsplit=1)[0].strip()
            return english_part if english_part else None

    # No separator found — treat the whole line as the English word/phrase.
    return line if line else None


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
        cache_path = _cache_mp3_path(english_word)
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            tmp_path = cache_path
            logger.info("TTS cache hit for %r → %s", english_word, cache_path)
        else:
            last_exc: Exception | None = None
            for attempt in range(1, TTS_MAX_RETRIES + 1):
                try:
                    await _throttle_tts()
                    tts = gTTS(text=english_word, lang=TTS_LANG, tld=TTS_TLD)

                    with tempfile.NamedTemporaryFile(
                        suffix=".mp3", delete=False
                    ) as tmp_file:
                        tmp_path = tmp_file.name

                    tts.save(tmp_path)
                    os.replace(tmp_path, cache_path)
                    tmp_path = cache_path
                    logger.info("Generated TTS for %r → %s", english_word, cache_path)
                    break
                except (gTTSError, Exception) as exc:  # noqa: BLE001
                    last_exc = exc
                    if _is_probable_429(exc) and attempt < TTS_MAX_RETRIES:
                        backoff = min(20.0, 2.0 ** (attempt - 1))
                        logger.warning(
                            "TTS rate-limited for %r (attempt %d/%d). Sleeping %.1fs.",
                            english_word,
                            attempt,
                            TTS_MAX_RETRIES,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    raise
            else:
                if last_exc is not None:
                    raise last_exc

        with open(tmp_path, "rb") as audio_file:
            # gTTS outputs MP3. Telegram "voice" messages (sendVoice) are expected
            # to be OGG/OPUS and may reject MP3, so we send as regular audio.
            await update.message.reply_audio(
                audio=audio_file,
                caption=f"🔊 *{english_word}*",
                parse_mode="Markdown",
            )

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to process %r: %s", english_word, exc)
        await update.message.reply_text(
            f"⚠️ *{english_word}* uchun audio yaratib bo'lmadi.",
            parse_mode="Markdown",
        )
    finally:
        # Only delete true temp files; cached files should be kept.
        if (
            tmp_path
            and os.path.exists(tmp_path)
            and os.path.abspath(tmp_path).startswith(os.path.abspath(tempfile.gettempdir()))
        ):
            os.remove(tmp_path)
            logger.debug("Deleted temp file: %s", tmp_path)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — send a welcome message explaining the expected input format."""
    welcome = (
        "👋 Salom! Men sizning talaffuz botingizman.\n\n"
        "Menga so'zlar ro'yxatini yuboring (har bir qatorda bitta, masalan: *banana — banan*), "
        "va men inglizcha qismining audiosini yuboraman!"
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
