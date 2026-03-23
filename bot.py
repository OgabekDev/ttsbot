import os
import sys
from io import BytesIO

from gtts import gTTS
from dotenv import load_dotenv

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

load_dotenv(os.path.join(PROJECT_DIR, ".env"))
BOT_TOKEN = os.getenv("BOT_TOKEN")

WELCOME_TEXT = (
    "Welcome to Audify Bot!\n\n"
    "Send me text in one of these formats:\n"
    "  English - Uzbek  (e.g. Apple - Olma)\n"
    "  English  (e.g. This is good)\n\n"
    "I'll reply with the English pronunciation audio."
)

ERROR_TEXT = (
    "Please write correct format:\n"
    "[English - Uzbek]\n"
    "[English]\n\n"
    "Error message: {error}"
)


def generate_audio(text: str) -> BytesIO:
    tts = gTTS(text=text, lang="en")
    audio_buffer = BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    return audio_buffer


def parse_words(text: str) -> list[tuple[str, str]]:
    """Returns list of (english, caption) tuples from message text."""
    lines = text.splitlines()
    word_lines = [l.strip() for l in lines if " - " in l]

    if not word_lines:
        return [(text.strip(), text.strip())]

    results = []
    for line in word_lines:
        english = line.split(" - ")[0].strip()
        if english:
            results.append((english, line))
    return results


# --- Polling mode (local development) ---

def run_polling():
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(WELCOME_TEXT)

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        try:
            if not text:
                raise ValueError("Empty message")
            for english, caption in parse_words(text):
                audio_buffer = generate_audio(english)
                audio_buffer.name = f"{english}.mp3"
                await update.message.reply_audio(
                    audio=audio_buffer,
                    caption=f"\U0001f50a {caption}",
                )
        except Exception as e:
            await update.message.reply_text(ERROR_TEXT.format(error=e))

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is running (polling mode)...")
    app.run_polling()


# --- Webhook mode (PythonAnywhere) ---

def create_flask_app():
    import requests as http_requests
    from flask import Flask, request as flask_request

    API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

    PROXIES = {}
    pa_proxy = os.getenv("https_proxy") or os.getenv("HTTPS_PROXY")
    if pa_proxy:
        PROXIES = {"https": pa_proxy}

    flask_app = Flask(__name__)

    def send_message(chat_id, text):
        http_requests.post(f"{API_BASE}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
        }, proxies=PROXIES)

    def send_audio(chat_id, audio_buffer, filename, caption):
        http_requests.post(
            f"{API_BASE}/sendAudio",
            data={"chat_id": chat_id, "caption": caption},
            files={"audio": (f"{filename}.mp3", audio_buffer, "audio/mpeg")},
            proxies=PROXIES,
        )

    def process_update(update_data):
        message = update_data.get("message", {})
        text = (message.get("text") or "").strip()
        chat_id = message.get("chat", {}).get("id")

        if not text or not chat_id:
            return

        if text == "/start":
            send_message(chat_id, WELCOME_TEXT)
            return

        try:
            for english, caption in parse_words(text):
                audio_buffer = generate_audio(english)
                send_audio(chat_id, audio_buffer, english, f"\U0001f50a {caption}")
        except Exception as e:
            send_message(chat_id, ERROR_TEXT.format(error=e))

    @flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        update_data = flask_request.get_json(force=True)
        process_update(update_data)
        return "ok"

    @flask_app.route("/")
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

    return flask_app


# Flask app instance for PythonAnywhere WSGI
app = create_flask_app()


if __name__ == "__main__":
    run_polling()
