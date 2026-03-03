import os
import sqlite3
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

# 1. CONFIGURATION
TELEGRAM_TOKEN = "8785914734:AAGDnXeKnVgmEqZpf3keMMQPUMk8eO3P-N4"
AI_API_KEY = "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"

client = OpenAI(api_key=AI_API_KEY)
app = Flask('')

# 2. WAKE UP SERVER (For 24/7 Uptime)
@app.route('/')
def home():
    return "NovaPump is Active!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# 3. MEMORY SYSTEM
def init_db():
    conn = sqlite3.connect('novapump.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS chat (user_id INTEGER, role TEXT, content TEXT)')
    conn.commit()
    conn.close()

def save_chat(user_id, role, content):
    conn = sqlite3.connect('novapump.db')
    c = conn.cursor()
    c.execute("INSERT INTO chat VALUES (?, ?, ?)", (user_id, role, content))
    conn.commit()
    conn.close()

def get_history(user_id):
    conn = sqlite3.connect('novapump.db')
    c = conn.cursor()
    c.execute("SELECT role, content FROM chat WHERE user_id=? ORDER BY ROWID DESC LIMIT 10", (user_id,))
    rows = c.fetchall()[::-1]
    conn.close()
    return [{"role": r, "content": c} for r, c in rows]

# 4. BOT RESPONSE LOGIC
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user_id = update.message.from_user.id
    user_text = update.message.text

    # Creator Check
    if any(word in user_text.lower() for word in ["creator", "made you", "who is marx"]):
        await update.message.reply_text("I was created by marxpayne. Contact him here: @marxpayne6")
        return

    # AI Brain Logic
    history = get_history(user_id)
    system_msg = {
        "role": "system",
        "content": "Your name is NovaPump. You are a genius crypto AI. Your creator is marxpayne (@marxpayne6). Be witty and helpful."
    }
    messages = [system_msg] + history + [{"role": "user", "content": user_text}]

    try:
        response = client.chat.completions.create(model="gpt-3.5-turbo", messages=messages)
        answer = response.choices[0].message.content
        save_chat(user_id, "user", user_text)
        save_chat(user_id, "assistant", answer)
        await update.message.reply_text(answer)
    except:
        await update.message.reply_text("I'm recalibrating. Try again!")

# 5. START
if __name__ == '__main__':
    init_db()
    keep_alive()
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    bot_app.run_polling()
