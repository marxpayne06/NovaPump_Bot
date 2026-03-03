import os
import sqlite3
import logging
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = "8785914734:AAGDnXeKnVgmEqZpf3keMMQPUMk8eO3P-N4"
GEMINI_API_KEY = "AIzaSyD740ZaetuuQ0ZyF4XLeLajlzPemItA_IE"

client = genai.Client(api_key=GEMINI_API_KEY)
app = Flask('')

@app.route('/')
def home(): return "NovaPump Gemini 3 is Active!"

def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=8080))
    t.daemon = True
    t.start()

# --- 2. KNOWLEDGE SYSTEM ---
def init_db():
    conn = sqlite3.connect('novapump.db')
    conn.cursor().execute('CREATE TABLE IF NOT EXISTS chat (user_id INTEGER, role TEXT, content TEXT)')
    conn.commit()
    conn.close()

def get_custom_knowledge():
    try:
        with open("novapump_knowledge.txt", "r") as f:
            return f.read()
    except:
        return "Creator: marxpayne (@marxpayne6). Name: NovaPump."

# --- 3. BOT BRAIN ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_id = update.message.from_user.id
    user_text = update.message.text

    # Quick Creator check
    if any(word in user_text.lower() for word in ["creator", "made you"]):
        await update.message.reply_text("I was created by marxpayne. Link: @marxpayne6")
        return

    knowledge = get_custom_knowledge()

    try:
        # Using Gemini 3 Flash (Latest 2026 Model)
        response = client.models.generate_content(
            model="gemini-3-flash",
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=f"Your name is NovaPump. Creator: marxpayne (@marxpayne6). {knowledge}"
            )
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text("NovaPump is processing... try again in a moment!")

# --- 4. START ---
if __name__ == '__main__':
    init_db()
    keep_alive()
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("NovaPump is starting...")
    bot_app.run_polling()
