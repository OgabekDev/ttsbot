import asyncio
from flask import Flask, request

from bot import BOT_TOKEN, start, handle_message
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

app = Flask(__name__)

# Build the telegram application
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Initialize the app once at import time
loop = asyncio.new_event_loop()
loop.run_until_complete(telegram_app.initialize())


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    loop.run_until_complete(telegram_app.process_update(update))
    return "ok"


@app.route("/")
def index():
    return "Bot is running!"
