import os
import sys
from io import BytesIO

from gtts import gTTS
from flask import Flask, request as flask_request
from dotenv import load_dotenv
from telegram import Update, Bot

# Ensure the project directory is in sys.path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

load_dotenv(os.path.join(PROJECT_DIR, ".env"))
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Flask(__name__)
bot = Bot(token=BOT_TOKEN)


def generate_audio(text: str) -> BytesIO:
    tts = gTTS(text=text, lang="en")
    audio_buffer = BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    return audio_buffer


def process_update(update_data):
    import asyncio
    loop = asyncio.new_event_loop()

    async def _handle():
        update = Update.de_json(update_data, bot)

        if update.message and update.message.text:
            text = update.message.text.strip()
            chat_id = update.message.chat_id

            if text == "/start":
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "Welcome to Audify Bot!\n\n"
                        "Send me text in one of these formats:\n"
                        "  English - Uzbek  (e.g. Apple - Olma)\n"
                        "  English  (e.g. This is good)\n\n"
                        "I'll reply with the English pronunciation audio."
                    ),
                )
                return

            try:
                if not text:
                    raise ValueError("Empty message")

                lines = text.splitlines()
                word_lines = [l.strip() for l in lines if " - " in l]

                if not word_lines:
                    english = text.strip()
                    audio_buffer = generate_audio(english)
                    audio_buffer.name = "audio.mp3"
                    await bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_buffer,
                        caption=f"🔊 {english}",
                    )
                else:
                    for line in word_lines:
                        english = line.split(" - ")[0].strip()
                        if not english:
                            continue
                        audio_buffer = generate_audio(english)
                        audio_buffer.name = "audio.mp3"
                        await bot.send_audio(
                            chat_id=chat_id,
                            audio=audio_buffer,
                            caption=f"🔊 {line}",
                        )

            except Exception as e:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "Please write correct format:\n"
                        "[English - Uzbek]\n"
                        "[English]\n\n"
                        f"Error message: {e}"
                    ),
                )

    loop.run_until_complete(_handle())
    loop.close()


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update_data = flask_request.get_json(force=True)
    process_update(update_data)
    return "ok"


@app.route("/")
def index():
    status = {"bot": "Audify Bot", "status": "running"}
    errors = []

    if not BOT_TOKEN:
        errors.append("BOT_TOKEN not loaded from .env")

    try:
        from gtts import gTTS  # noqa: F401
    except ImportError:
        errors.append("gTTS package not installed")

    if errors:
        status["status"] = "error"
        status["errors"] = errors

    return status
