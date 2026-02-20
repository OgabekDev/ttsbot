"""
Flask webhook receiver for the Telegram Vocabulary TTS Bot.
Designed for PythonAnywhere free-tier deployment.
"""

import asyncio
import logging

from flask import Flask, request, jsonify
from telegram import Update

from bot import get_application

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Async helper  —  PythonAnywhere runs WSGI (synchronous), but
# python-telegram-bot is fully async.  We bridge the gap by creating
# a fresh event loop for each call.
# ---------------------------------------------------------------------------


def run_async(coro):
    """Run an async coroutine from synchronous Flask code."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

bot_app = get_application()
run_async(bot_app.initialize())
logger.info("Telegram bot application initialised.")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return "Bot is running!"


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive an update from Telegram and process it."""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot_app.bot)
        run_async(bot_app.process_update(update))
        return jsonify({"status": "ok"})
    except Exception as exc:
        logger.error("Error processing webhook: %s", exc, exc_info=True)
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/set_webhook")
def set_webhook():
    """Set the Telegram webhook URL.

    Usage:
        /set_webhook?url=https://YOURUSERNAME.pythonanywhere.com/webhook
    """
    webhook_url = request.args.get("url")
    if not webhook_url:
        return (
            "Provide a 'url' query parameter.  Example:\n"
            "/set_webhook?url=https://YOURUSERNAME.pythonanywhere.com/webhook"
        )

    try:
        success = run_async(bot_app.bot.set_webhook(url=webhook_url))
        if success:
            return f"Webhook set to {webhook_url}"
        return "Telegram returned failure when setting webhook.", 500
    except Exception as exc:
        logger.error("set_webhook error: %s", exc, exc_info=True)
        return f"Error setting webhook: {exc}", 500


# ---------------------------------------------------------------------------
# Local development
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(port=5000)
