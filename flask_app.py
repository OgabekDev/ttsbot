import os
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from asgiref.sync import async_to_sync

# Import your bot application logic
from bot import get_application, BOT_TOKEN

app = Flask(__name__)

# Initialize the Telegram Application
bot_app = get_application()

# We need to run the initialization once
# Since Flask handles requests in threads, we use async_to_sync for bot methods
async_to_sync(bot_app.initialize)()

@app.route("/")
def index():
    return "Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive updates from Telegram."""
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        
        # Process the update asynchronously
        async_to_sync(bot_app.process_update)(update)
        
        return jsonify({"status": "ok"})
    return "Invalid request", 400

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    """Convenience route to set the webhook URL."""
    # Example: https://yourusername.pythonanywhere.com/webhook
    # You must replace this with your actual PythonAnywhere URL
    webhook_url = request.args.get("url")
    if not webhook_url:
        return "Please provide a 'url' parameter. Example: /set_webhook?url=https://yourname.pythonanywhere.com/webhook"
    
    success = async_to_sync(bot_app.bot.set_webhook)(url=webhook_url)
    if success:
        return f"Webhook successfully set to {webhook_url}"
    else:
        return "Failed to set webhook."

if __name__ == "__main__":
    # Local development server
    app.run(port=5000)
