import os
import sqlite3
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

# --- CONFIGURATION (INTEGRATED) ---
TELEGRAM_TOKEN = "8785914734:AAGDnXeKnVgmEqZpf3keMMQPUMk8eO3P-N4"
GROQ_API_KEY = "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"
CREATOR_HANDLE = "@Marx_payne2"

client = Groq(api_key=GROQ_API_KEY)
app = Flask('')

@app.route('/')
def home(): return "NovaPump Groq (Long-Term Memory) is Active!"

def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=8080))
    t.daemon = True
    t.start()

# --- DATABASE SYSTEM (SQLITE) ---
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
    # Increased limit to 30 messages
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
            messages=[{"role": "system", "content": "Summarize the key facts from this chat into 3 sentences. Focus on user preferences and shared info."},
                      {"role": "user", "content": text_to_summarize}],
            model="llama-3.3-70b-versatile",
        )
        new_summary = completion.choices[0].message.content
        conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO summaries (user_id, summary) VALUES (?, ?)", (user_id, new_summary))
        cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Summarization Error: {e}")

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 Hello! I'm NovaPump.\n\n"
        "I'm here to chat and help you out. I remember our past conversations, "
        "so we can just pick up where we left off. What's on your mind?"
    )
    await update.message.reply_text(welcome_text)

# --- CHAT LOGIC ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_id = update.message.from_user.id
    user_text = update.message.text
    
    # Check for issue reporting or creator inquiries
    support_keywords = ["issue", "problem", "report", "creator", "admin", "contact", "talk to developer"]
    if any(word in user_text.lower() for word in support_keywords):
        await update.message.reply_text(f"For any issues, reports, or to speak with my creator, please contact {CREATOR_HANDLE} directly.")
        return

    history = get_history(user_id)
    summary = get_summary(user_id)

    # Trigger summarization when history reaches the 30-message limit
    if len(history) >= 29:
        summarize_chat(user_id, history)
        history = []
        summary = get_summary(user_id)

    # System Prompt with your specific personality rules
    system_prompt = (
        f"You are NovaPump. Your creator is {CREATOR_HANDLE}. "
        "RULES: \n"
        "1. Be chill, natural, and helpful.\n"
        "2. Do NOT mention your name or creator unless asked.\n"
        "3. Only talk about crypto if the user brings it up or it is necessary for the context.\n"
        "4. If a user has a technical problem, tell them to contact your creator.\n"
        f"Long-term memory summary: {summary}"
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
        await update.message.reply_text("I had a brief memory glitch. Could you say that again?")

if __name__ == '__main__':
    init_db()
    keep_alive()
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Add /start command and text message handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("NovaPump is live and remembers everything...")
    bot_app.run_polling()
