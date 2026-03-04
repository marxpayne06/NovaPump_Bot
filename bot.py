import os
import sqlite3
from threading import Thread
from flask import Flask
from telegram import Update, ChatPermissions, constants
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "8785914734:AAGDnXeKnVgmEqZpf3keMMQPUMk8eO3P-N4"
GROQ_API_KEY = "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"
CREATOR_HANDLE = "@Marx_payne2"
BLACKLIST = ["scam", "spam", "f**k", "sh*t", "idiot"] # Add your bad words here

client = Groq(api_key=GROQ_API_KEY)
app = Flask('')

@app.route('/')
def home(): return "NovaPump Ultra Admin is Active!"

def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=8080))
    t.daemon = True
    t.start()

# --- DATABASE & STRIKE SYSTEM ---
def init_db():
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS history (user_id INTEGER, role TEXT, content TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS strikes (user_id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()

def update_strikes(user_id):
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO strikes (user_id, count) VALUES (?, 0)", (user_id,))
    cursor.execute("UPDATE strikes SET count = count + 1 WHERE user_id = ?", (user_id,))
    cursor.execute("SELECT count FROM strikes WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return count

# --- ADMIN PERMISSION CHECK ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return user.status in [constants.ChatMemberStatus.ADMINISTRATOR, constants.ChatMemberStatus.OWNER]

# --- MODERATION COMMANDS ---
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the user to mute them.")
        return
    target = update.message.reply_to_message.from_user
    # Explicitly set ALL permissions to False
    await context.bot.restrict_chat_member(
        update.effective_chat.id, 
        target.id, 
        permissions=ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_send_other_messages=False)
    )
    await update.message.reply_text(f"🔇 {target.first_name} has been muted.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    await context.bot.ban_chat_member(update.effective_chat.id, target.id)
    await update.message.reply_text(f"🚫 {target.first_name} has been banned.")

async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = "📜 *Group Rules*\n1. No spam\n2. No insults\n3. Respect the Creator."
    await update.message.reply_text(rules, parse_mode='Markdown')

# --- MAIN MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_id = update.message.from_user.id
    user_text = update.message.text
    chat_id = update.effective_chat.id

    # 1. AUTO-MODERATION (Strikes)
    if any(word in user_text.lower() for word in BLACKLIST):
        await context.bot.delete_message(chat_id, update.message.message_id)
        strikes = update_strikes(user_id)
        
        if strikes == 1:
            await context.bot.send_message(chat_id, f"⚠️ Warning {update.message.from_user.first_name}! Strike 1. No bad words.")
        elif strikes == 2:
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
            await context.bot.send_message(chat_id, f"🔇 Strike 2! {update.message.from_user.first_name} muted for 24 hours.")
        else:
            await context.bot.ban_chat_member(chat_id, user_id)
            await context.bot.send_message(chat_id, f"🚫 Strike 3! {update.message.from_user.first_name} has been banned.")
        return

    # 2. AI RESPONSE LOGIC
    # (Existing AI logic here - only replies if tagged or private)
    bot_username = (await context.bot.get_me()).username
    if update.message.chat.type != constants.ChatType.PRIVATE:
        if f"@{bot_username}" not in user_text:
            return
    
    # ... (AI generate_content part) ...
    await update.message.reply_text("I'm here! What do you need?")

if __name__ == '__main__':
    init_db()
    keep_alive()
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler("rules", show_rules))
    bot_app.add_handler(CommandHandler("mute", mute))
    bot_app.add_handler(CommandHandler("ban", ban))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    bot_app.run_polling()
