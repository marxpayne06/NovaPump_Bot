import os
import sqlite3
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update, ChatPermissions, constants
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "8785914734:AAGDnXeKnVgmEqZpf3keMMQPUMk8eO3P-N4"
GROQ_API_KEY = "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"
CREATOR_HANDLE = "@Marx_payne2"
BLACKLIST = ["scam", "spam", "f**k", "sh*t"]

# --- CUSTOMIZE YOUR RULES HERE ---
GROUP_RULES = (
    "📜 *Group Rules*\n\n"
    "1. Be respectful to everyone.\n"
    "2. No spamming or unauthorized links.\n"
    "3. No offensive language (Auto-deleted).\n"
    f"4. For support, contact {CREATOR_HANDLE}.\n\n"
    "Failure to follow rules may lead to a mute or ban."
)

client = Groq(api_key=GROQ_API_KEY)
app = Flask('')

@app.route('/')
def home(): return "NovaPump Ultimate Mode Active!"

def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=8080))
    t.daemon = True
    t.start()

# --- DATABASE & MEMORY ---
def init_db():
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS history (user_id INTEGER, role TEXT, content TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS summaries (user_id INTEGER PRIMARY KEY, summary TEXT)')
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

# --- WELCOME & AUTO-CLEAN ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == (await context.bot.get_me()).id:
            continue
            
        welcome_text = f"👋 Welcome {member.first_name}! Check out the /rules and enjoy the community."
        await update.message.reply_text(welcome_text)
        
        # Optional: Delete the "X joined the group" service message to keep chat clean
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except: pass

# --- RULES COMMAND ---
async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(GROUP_RULES, parse_mode='Markdown')

# --- ADMIN FUNCTIONS ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return user.status in [constants.ChatMemberStatus.ADMINISTRATOR, constants.ChatMemberStatus.OWNER]

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the user to mute them.")
        return
    target = update.message.reply_to_message.from_user
    await context.bot.restrict_chat_member(update.effective_chat.id, target.id, permissions=ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"🔇 {target.first_name} muted.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the user to unmute them.")
        return
    target = update.message.reply_to_message.from_user
    await context.bot.restrict_chat_member(update.effective_chat.id, target.id, permissions=ChatPermissions.all_permissions())
    await update.message.reply_text(f"🔊 {target.first_name} unmuted.")

# --- CHAT & MODERATION ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_id = update.message.from_user.id
    user_text = update.message.text
    chat_type = update.message.chat.type
    bot_obj = await context.bot.get_me()

    # 1. AUTO-MODERATION
    if any(word in user_text.lower() for word in BLACKLIST):
        try:
            await context.bot.delete_message(update.effective_chat.id, update.message.message_id)
            return
        except: pass

    # 2. GROUP LOGIC (Reply if mentioned OR if user replies to bot)
    is_reply_to_bot = update.message.reply_to_message and update.message.reply_to_message.from_user.id == bot_obj.id
    
    if chat_type in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP]:
        if f"@{bot_obj.username}" not in user_text and not is_reply_to_bot:
            return

    # 3. AI RESPONSE
    history = get_history(user_id)
    messages = [{"role": "system", "content": f"You are NovaPump. Creator: {CREATOR_HANDLE}. Be chill."}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        chat_completion = client.chat.completions.create(messages=messages, model="llama-3.3-70b-versatile")
        response = chat_completion.choices[0].message.content
        save_message(user_id, "user", user_text)
        save_message(user_id, "assistant", response)
        await update.message.reply_text(response)
    except:
        await update.message.reply_text("Thinking... try again.")

if __name__ == '__main__':
    init_db()
    keep_alive()
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Handlers
    bot_app.add_handler(CommandHandler("start", show_rules)) # Start also shows rules
    bot_app.add_handler(CommandHandler("rules", show_rules))
    bot_app.add_handler(CommandHandler("mute", mute))
    bot_app.add_handler(CommandHandler("unmute", unmute))
    bot_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("NovaPump is fully operational.")
    bot_app.run_polling()
