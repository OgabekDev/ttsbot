import os
import sys
from io import BytesIO

import requests as http_requests
from gtts import gTTS
from flask import Flask, request as flask_request
from dotenv import load_dotenv

# Ensure the project directory is in sys.path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

load_dotenv(os.path.join(PROJECT_DIR, ".env"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)


def generate_audio(text: str) -> BytesIO:
    tts = gTTS(text=text, lang="en")
    audio_buffer = BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    return audio_buffer


def send_message(chat_id, text):
    http_requests.post(f"{API_BASE}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
    })


def send_audio(chat_id, audio_buffer, caption):
    http_requests.post(
        f"{API_BASE}/sendAudio",
        data={"chat_id": chat_id, "caption": caption},
        files={"audio": ("audio.mp3", audio_buffer, "audio/mpeg")},
    )


def process_update(update_data):
    message = update_data.get("message", {})
    text = (message.get("text") or "").strip()
    chat_id = message.get("chat", {}).get("id")

    if not text or not chat_id:
        return

    if text == "/start":
        send_message(
            chat_id,
            "Welcome to Audify Bot!\n\n"
            "Send me text in one of these formats:\n"
            "  English - Uzbek  (e.g. Apple - Olma)\n"
            "  English  (e.g. This is good)\n\n"
            "I'll reply with the English pronunciation audio.",
        )
        return

    try:
        lines = text.splitlines()
        word_lines = [l.strip() for l in lines if " - " in l]

        if not word_lines:
            audio_buffer = generate_audio(text)
            send_audio(chat_id, audio_buffer, f"\U0001f50a {text}")
        else:
            for line in word_lines:
                english = line.split(" - ")[0].strip()
                if not english:
                    continue
                audio_buffer = generate_audio(english)
                send_audio(chat_id, audio_buffer, f"\U0001f50a {line}")

    except Exception as e:
        send_message(
            chat_id,
            "Please write correct format:\n"
            "[English - Uzbek]\n"
            "[English]\n\n"
            f"Error message: {e}",
        )


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
