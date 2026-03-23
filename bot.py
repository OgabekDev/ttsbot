import os
import asyncio
from io import BytesIO

import edge_tts
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

VOICE = "en-US-AriaNeural"


async def generate_audio(text: str) -> BytesIO:
    communicate = edge_tts.Communicate(text, VOICE)
    audio_buffer = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.write(chunk["data"])
    audio_buffer.seek(0)
    return audio_buffer


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Audify Bot!\n\n"
        "Send me text in one of these formats:\n"
        "  English - Uzbek  (e.g. Apple - Olma)\n"
        "  English  (e.g. This is good)\n\n"
        "I'll reply with the English pronunciation audio."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    try:
        if not text:
            raise ValueError("Empty message")

        # Parse: take the part before " - " as English
        english = text.split(" - ")[0].strip()

        if not english:
            raise ValueError("English part is empty")

        audio_buffer = await generate_audio(english)
        await update.message.reply_voice(voice=audio_buffer)

    except Exception as e:
        await update.message.reply_text(
            "Please write correct format:\n"
            "[English - Uzbek]\n"
            "[English]\n\n"
            f"Error message: {e}"
        )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
