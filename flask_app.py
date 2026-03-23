import os
import sys
import asyncio
from io import BytesIO

import edge_tts
from flask import Flask, request as flask_request
from dotenv import load_dotenv
from telegram import Update, Bot

# Ensure the project directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
VOICE = "en-US-AriaNeural"

app = Flask(__name__)
bot = Bot(token=BOT_TOKEN)

loop = asyncio.new_event_loop()


async def generate_audio(text: str) -> BytesIO:
    communicate = edge_tts.Communicate(text, VOICE)
    audio_buffer = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.write(chunk["data"])
    audio_buffer.seek(0)
    return audio_buffer


async def process_update(update_data):
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

            english = text.split(" - ")[0].strip()
            if not english:
                raise ValueError("English part is empty")

            audio_buffer = await generate_audio(english)
            await bot.send_voice(chat_id=chat_id, voice=audio_buffer)

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


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update_data = flask_request.get_json(force=True)
    loop.run_until_complete(process_update(update_data))
    return "ok"


@app.route("/")
def index():
    return "Bot is running!"
