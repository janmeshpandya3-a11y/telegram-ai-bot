import os
import re
import json
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from notion_client import Client as NotionClient
from bs4 import BeautifulSoup

# -----------------------------
# Load Environment Variables
# -----------------------------
load_dotenv()
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
HF_API_TOKEN = os.environ.get("HF_API_TOKEN")  # Hugging Face token (optional)
AI_TITLE_API = os.environ.get("AI_TITLE_API")  # Optional endpoint for title generation

# -----------------------------
# Hugging Face categories for link classification
# -----------------------------
TYPES = ["Shopping", "Tasks", "Reminders", "Reading", "Ideas", "Other"]
SUBCATEGORIES = [
    "Grocery", "Household", "Gifts", "Work", "Personal",
    "Articles", "Books", "Projects", "Hobbies", "Misc"
]

# -----------------------------
# Load rules
# -----------------------------
try:
    with open("rules.json", "r") as f:
        RULES = json.load(f)
except FileNotFoundError:
    RULES = {}

# -----------------------------
# Initialize Notion client
# -----------------------------
notion = NotionClient(auth=NOTION_TOKEN)

# -----------------------------
# Helper functions
# -----------------------------
def apply_rules(message_text):
    for keyword, mapping in RULES.items():
        if keyword.lower() in message_text.lower():
            return mapping
    return None

def get_page_title_from_url(url):
    """
    Scrape the webpage and generate a sensible title.
    Uses AI if AI_TITLE_API provided, else uses <title> tag.
    """
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        title = soup.title.string.strip() if soup.title else url
        # Optional: send to AI endpoint for a better title
        if AI_TITLE_API:
            response = requests.post(AI_TITLE_API, json={"text": title})
            data = response.json()
            if "title" in data:
                title = data["title"]
        return title
    except Exception:
        return url  # fallback

def classify_link_hf(message_text):
    urls = re.findall(r"https?://\S+", message_text)
    if not urls:
        return None

    if not HF_API_TOKEN:
        return {"type": "Other", "subcategory": "Misc", "name": message_text, "url": urls[0]}

    candidate_labels = [f"{t}: {s}" for t in TYPES for s in SUBCATEGORIES]
    payload = {
        "inputs": message_text,
        "parameters": {"candidate_labels": candidate_labels},
    }

    response = requests.post(
        "https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
        headers={"Authorization": f"Bearer {HF_API_TOKEN}", "Content-Type": "application/json"},
        json=payload
    )
    data = response.json()
    if "labels" in data:
        best_label = data["labels"][0]
        if ":" in best_label:
            type_name, subcat_name = map(str.strip, best_label.split(":"))
        else:
            type_name, subcat_name = "Other", "Misc"
        title = get_page_title_from_url(urls[0])
        return {"type": type_name, "subcategory": subcat_name, "name": title, "url": urls[0]}
    else:
        title = get_page_title_from_url(urls[0])
        return {"type": "Other", "subcategory": "Misc", "name": title, "url": urls[0]}

def classify_message(message_text):
    # Apply rules first
    rule_result = apply_rules(message_text)
    if rule_result:
        rule_result["name"] = message_text
        rule_result["url"] = ""
        return rule_result

    # Check for links
    if re.search(r"https?://\S+", message_text):
        return classify_link_hf(message_text)

    # Fallback: generate sensible title from message
    title = message_text if len(message_text) < 100 else message_text[:100] + "..."
    return {"type": "Other", "subcategory": "Misc", "name": title, "url": ""}

def save_to_notion(item):
    """
    Save to Notion database with:
    - Type (Select)
    - Subcategory (Select)
    - Name (Title)
    - URL (URL property)
    """
    page = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Type": {"select": {"name": item["type"]}},
            "Subcategory": {"select": {"name": item["subcategory"]}},
            "Name": {"title": [{"text": {"content": item["name"]}}]},
            "URL": {"url": item.get("url", "")}
        }
    }
    notion.pages.create(**page)

# -----------------------------
# Telegram handler
# -----------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    item = classify_message(text)
    save_to_notion(item)
    await update.message.reply_text(f"Saved to Notion! ({item['type']} / {item['subcategory']})")

# -----------------------------
# Main app
# -----------------------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("Bot started. Polling for messages...")
    app.run_polling()