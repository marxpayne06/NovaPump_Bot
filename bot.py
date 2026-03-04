import os
import sqlite3
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "8785914734:AAGDnXeKnVgmEqZpf3keMMQPUMk8eO3P-N4"
GROQ_API_KEY = "YOUR_GROQ_KEY_HERE"
CREATOR_HANDLE = "@Marx_payne2"

client = Groq(api_key=GROQ_API_KEY)
app = Flask('')

@app.route('/')
def home(): return "NovaPump with Advanced Memory is Active!"

def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=8080))
    t.daemon = True
    t.start()

# --- DATABASE SYSTEM ---
def init_db():
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS history 
                      (user_id INTEGER, role TEXT, content TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS summaries 
                      (user_id INTEGER PRIMARY KEY, summary TEXT)''')
    conn.commit()
    conn.close()

def save_message(user_id, role, content):
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history VALUES (?, ?, ?)", (user_id, role, content))
    conn.commit()
    conn.close()

def get_history(user_id):
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM history WHERE user_id = ? ORDER BY rowid DESC LIMIT 30", (user_id,))
    rows = cursor.fetchall()[::-1]
    conn.close()
    return [{"role": r, "content": c} for r, c in rows]

def get_summary(user_id):
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT summary FROM summaries WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else ""

# --- SUMMARIZATION ENGINE ---
def summarize_chat(user_id, history):
    text_to_summarize = "\n".join([f"{m['role']}: {m['content']}" for m in history])
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "system", "content": "Summarize the key facts from this chat into 3 sentences."},
                      {"role": "user", "content": text_to_summarize}],
            model="llama-3.3-70b-versatile",
        )
        new_summary = completion.choices[0].message.content
        conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO summaries (user_id, summary) VALUES (?, ?)", (user_id, new_summary))
        # Clear old history to prevent bloat
        cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Summarization Error: {e}")

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 Hello! I'm NovaPump.\n\n"
        "I'm here to chat and help you out. I've got a long-term memory, "
        "so feel free to pick up where we left off. If you need anything specific, just ask!"
    )
    await update.message.reply_text(welcome_text)

# --- CHAT LOGIC ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_id = update.message.from_user.id
    user_text = update.message.text
    
    # 1. Check for issues/creator support
    support_keywords = ["issue", "problem", "report", "creator", "admin", "contact"]
    if any(word in user_text.lower() for word in support_keywords):
        await update.message.reply_text(f"If you have an issue or want to speak with my creator, contact {CREATOR_HANDLE} directly.")
        return

    history = get_history(user_id)
    summary = get_summary(user_id)

    # 2. Trigger summarization if history is getting long
    if len(history) >= 29:
        summarize_chat(user_id, history)
        history = [] # Reset history after summarization
        summary = get_summary(user_id)

    # 3. Build the System Prompt
    system_prompt = (
        f"You are NovaPump. Your creator is {CREATOR_HANDLE}. "
        "Personality: Chill, helpful, and natural. Do NOT mention your name or creator constantly. "
        "Only talk about crypto if the user asks. If they have a problem, tell them to contact your creator. "
        f"Context from past conversations: {summary}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        chat_completion = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
        )
        response = chat_completion.choices[0].message.content
        
        save_message(user_id, "user", user_text)
        save_message(user_id, "assistant", response)
        
        await update.message.reply_text(response)
    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text("I'm having a quick reset. Try that again?")

if __name__ == '__main__':
    init_db()
    keep_alive()
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("NovaPump is live with Long-Term Memory...")
    bot_app.run_polling()
