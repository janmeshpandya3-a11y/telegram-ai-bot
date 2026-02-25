import os
import json
import requests
from notion_client import Client
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

# Load environment variables
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

# Initialize Notion client
notion = Client(auth=NOTION_TOKEN)

# Load rules
with open("rules.json") as f:
    rules = json.load(f)

# Simple helper: check rules first
def apply_rules(text):
    for prefix, forced_type in rules.get("force_prefix", {}).items():
        if text.startswith(prefix):
            return {"type": forced_type}
    for kw, override in rules.get("keyword_overrides", {}).items():
        if kw.lower() in text.lower():
            return override
    for ignore in rules.get("ignore_if_contains", []):
        if ignore.lower() in text.lower():
            return {"ignore": True}
    return {}

# AI classification function (call Hugging Face or OpenAI)
def classify_with_ai(text):
    # Example placeholder using HF inference API
    # Replace with your chosen AI model
    return {
        "type": "SHOPPING",
        "subcategory": "Groceries",
        "title": text
    }

# Function to save to Notion
def save_to_notion(data):
    page = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": data.get("title", "Unnamed")}}]},
            "Type": {"select": {"name": data.get("type", "Other")}},
            "Subcategory": {"select": {"name": data.get("subcategory", "Other")}},
            "Source": {"select": {"name": "Telegram Text"}}
        }
    }
    notion.pages.create(**page)

# Telegram handler
def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    if not text:
        return

    # Apply rules
    rule_result = apply_rules(text)
    if rule_result.get("ignore"):
        return

    # Use AI if no forced type
    if "type" not in rule_result:
        ai_result = classify_with_ai(text)
    else:
        ai_result = rule_result
        ai_result["title"] = text

    save_to_notion(ai_result)
    update.message.reply_text(f"Saved to Notion: {ai_result['type']} / {ai_result.get('subcategory','')}")

# Start bot
updater = Updater(TELEGRAM_TOKEN)
dp = updater.dispatcher
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

updater.start_polling()
updater.idle()