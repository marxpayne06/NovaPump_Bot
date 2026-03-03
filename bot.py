import os
import sqlite3
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from groq import Groq

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "8785914734:AAGDnXeKnVgmEqZpf3keMMQPUMk8eO3P-N4"
GROQ_API_KEY = "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"

client = Groq(api_key=GROQ_API_KEY)
app = Flask('')

@app.route('/')
def home(): return "NovaPump Groq is Active!"

def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=8080))
    t.daemon = True
    t.start()

# --- KNOWLEDGE ---
def get_custom_knowledge():
    try:
        with open("novapump_knowledge.txt", "r") as f: return f.read()
    except: return "Identity: NovaPump. Creator: marxpayne (@marxpayne6)."

# --- CHAT LOGIC ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_text = update.message.text
    knowledge = get_custom_knowledge()

    try:
        # Llama 3.3 70B is incredibly smart and fast
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": f"You are NovaPump. Creator: marxpayne. Info: {knowledge}"},
                {"role": "user", "content": user_text}
            ],
            model="llama-3.3-70b-versatile",
        )
        response = chat_completion.choices[0].message.content
        await update.message.reply_text(response)
    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text("NovaPump is rebooting... try again!")

if __name__ == '__main__':
    keep_alive()
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    bot_app.run_polling()
