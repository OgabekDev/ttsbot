"""
Flask webhook receiver for the Telegram Vocabulary TTS Bot.
Designed for PythonAnywhere free-tier deployment.

Key design:
    • Returns 200 OK to Telegram IMMEDIATELY so it never retries.
    • Processes the update synchronously (within the request) to avoid
      daemon threads being killed on worker recycle.
    • Deduplicates updates with a FILE-BASED set of recently seen update IDs
      so state survives WSGI worker restarts.
"""

import asyncio
import json
import logging
import os
import threading

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
# python-telegram-bot is fully async.  We keep ONE persistent event
# loop alive so httpx (used internally) doesn't hit "loop is closed".
# ---------------------------------------------------------------------------

_loop = asyncio.new_event_loop()
_lock = threading.Lock()


def run_async(coro):
    """Run an async coroutine from synchronous Flask code."""
    with _lock:
        return _loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# File-based update deduplication (survives WSGI worker restarts)
# ---------------------------------------------------------------------------

_MAX_SEEN = 2000
_DEDUP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".seen_updates.json")
_seen_lock = threading.Lock()


def _load_seen() -> list[int]:
    """Load the list of seen update IDs from disk."""
    try:
        if os.path.exists(_DEDUP_FILE):
            with open(_DEDUP_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception:
        pass
    return []


def _save_seen(seen: list[int]) -> None:
    """Save the list of seen update IDs to disk."""
    try:
        with open(_DEDUP_FILE, "w") as f:
            json.dump(seen, f)
    except Exception as exc:
        logger.error("Failed to save dedup file: %s", exc)


def _is_duplicate(update_id: int) -> bool:
    """Return True if we already started processing this update_id.

    Uses file-based persistence so state survives WSGI worker restarts.
    """
    with _seen_lock:
        seen = _load_seen()
        if update_id in seen:
            return True
        seen.append(update_id)
        # Trim to bounded size — keep only the most recent entries
        if len(seen) > _MAX_SEEN:
            seen = seen[-_MAX_SEEN:]
        _save_seen(seen)
        return False


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
    """Receive an update from Telegram.

    Returns 200 AFTER processing the update synchronously.
    Deduplication prevents re-processing if Telegram retries.
    """
    try:
        data = request.get_json(force=True)
        update_id = data.get("update_id")

        # --- Deduplication: skip if already seen ---
        if update_id is not None and _is_duplicate(update_id):
            logger.warning("Duplicate update_id %s — skipping.", update_id)
            return jsonify({"status": "duplicate_skipped"})

        # --- Process synchronously (no background thread) ---
        # This ensures the work completes before the WSGI worker
        # can be recycled, preventing partial-then-full replays.
        try:
            update = Update.de_json(data, bot_app.bot)
            run_async(bot_app.process_update(update))
            logger.info("Processing complete for update %s", update_id)
        except Exception as exc:
            logger.error("Error processing update %s: %s", update_id, exc, exc_info=True)

        return jsonify({"status": "ok"})
    except Exception as exc:
        logger.error("Error in webhook endpoint: %s", exc, exc_info=True)
        # Still return 200 to prevent Telegram from retrying.
        return jsonify({"status": "error", "message": str(exc)})


@app.route("/set_webhook")
def set_webhook():
    """Set the Telegram webhook URL.

    Usage:
        /set_webhook?url=https://alienroller.pythonanywhere.com/webhook
    """
    webhook_url = request.args.get("url")
    if not webhook_url:
        return (
            "Provide a 'url' query parameter.  Example:\n"
            "/set_webhook?url=https://alienroller.pythonanywhere.com/webhook"
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
