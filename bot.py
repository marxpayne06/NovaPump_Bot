import os
import sqlite3
from threading import Thread
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ChatMemberHandler, filters, ContextTypes
from telegram.constants import ChatMemberStatus
from datetime import datetime, timedelta
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
    # --- GROUP MANAGEMENT TABLES ---
    cursor.execute('''CREATE TABLE IF NOT EXISTS welcome_messages
                      (chat_id INTEGER PRIMARY KEY, welcome TEXT, goodbye TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_filters
                      (chat_id INTEGER, keyword TEXT, response TEXT,
                       PRIMARY KEY (chat_id, keyword))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_rules
                      (chat_id INTEGER PRIMARY KEY, rules TEXT)''')
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

    # --- Check filters before AI response ---
    cid = update.effective_chat.id
    text_lower = user_text.lower()
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT keyword, response FROM chat_filters WHERE chat_id = ?", (cid,))
    active_filters = cursor.fetchall()
    conn.close()
    for keyword, response in active_filters:
        if keyword in text_lower:
            await update.message.reply_text(response)
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


# ============================================================
# GROUP MANAGEMENT FEATURES (added below — original code untouched)
# ============================================================

# --- Helpers ---

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    uid = user_id or update.effective_user.id
    admins = await update.effective_chat.get_administrators()
    return any(a.user.id == uid for a in admins)

async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not await is_admin(update, context):
        await update.message.reply_text("⛔ You need to be an admin to use this command.")
        return False
    return True

def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.reply_to_message:
        u = msg.reply_to_message.from_user
        return u.id, u.full_name
    if context.args:
        arg = context.args[0]
        if arg.lstrip("-").isdigit():
            return int(arg), arg
    return None, None

def format_welcome(template: str, user, chat) -> str:
    name = user.full_name
    username = f"@{user.username}" if user.username else name
    return (
        template
        .replace("{name}", name)
        .replace("{username}", username)
        .replace("{chat}", chat.title or "this group")
        .replace("{id}", str(user.id))
    )

# --- Welcome / Goodbye ---

async def on_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    chat = result.chat
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    user = result.new_chat_member.user

    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT welcome, goodbye FROM welcome_messages WHERE chat_id = ?", (chat.id,))
    row = cursor.fetchone()
    conn.close()

    welcome_tmpl = row[0] if row and row[0] else "👋 Welcome, {name}! Glad to have you in {chat}."
    goodbye_tmpl = row[1] if row and row[1] else "👋 {name} has left {chat}. Goodbye!"

    if old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED) and \
       new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        await context.bot.send_message(chat.id, format_welcome(welcome_tmpl, user, chat))

    elif old_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR) and \
         new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        await context.bot.send_message(chat.id, format_welcome(goodbye_tmpl, user, chat))

async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: /setwelcome <message>\nPlaceholders: {name} {username} {chat} {id}")
        return
    msg = " ".join(context.args)
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO welcome_messages (chat_id, welcome) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET welcome=excluded.welcome",
                   (update.effective_chat.id, msg))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ Welcome message updated!")

async def set_goodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: /setgoodbye <message>\nPlaceholders: {name} {username} {chat} {id}")
        return
    msg = " ".join(context.args)
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO welcome_messages (chat_id, goodbye) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET goodbye=excluded.goodbye",
                   (update.effective_chat.id, msg))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ Goodbye message updated!")

async def reset_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE welcome_messages SET welcome = NULL WHERE chat_id = ?", (update.effective_chat.id,))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ Welcome message reset to default.")

# --- Bans / Mutes / Kicks ---

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    user_id, name = get_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a user or provide their ID to ban."); return
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    await update.effective_chat.ban_member(user_id)
    await update.message.reply_text(f"🚫 <b>{name}</b> has been banned.\n📝 Reason: {reason}", parse_mode="HTML")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    user_id, name = get_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a user or provide their ID to unban."); return
    await update.effective_chat.unban_member(user_id)
    await update.message.reply_text(f"✅ <b>{name}</b> has been unbanned.", parse_mode="HTML")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    user_id, name = get_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a user or provide their ID to kick."); return
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    await update.effective_chat.ban_member(user_id)
    await update.effective_chat.unban_member(user_id)
    await update.message.reply_text(f"👢 <b>{name}</b> has been kicked.\n📝 Reason: {reason}", parse_mode="HTML")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    user_id, name = get_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a user or provide their ID to mute."); return
    until = None
    duration_str = ""
    if context.args:
        raw = context.args[-1]
        try:
            if raw.endswith("m"):
                until = datetime.now() + timedelta(minutes=int(raw[:-1])); duration_str = f" for {raw[:-1]} minute(s)"
            elif raw.endswith("h"):
                until = datetime.now() + timedelta(hours=int(raw[:-1])); duration_str = f" for {raw[:-1]} hour(s)"
            elif raw.endswith("d"):
                until = datetime.now() + timedelta(days=int(raw[:-1])); duration_str = f" for {raw[:-1]} day(s)"
        except ValueError:
            pass
    await update.effective_chat.restrict_member(user_id, ChatPermissions(can_send_messages=False), until_date=until)
    await update.message.reply_text(f"🔇 <b>{name}</b> has been muted{duration_str}.", parse_mode="HTML")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    user_id, name = get_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a user or provide their ID to unmute."); return
    perms = ChatPermissions(can_send_messages=True, can_send_polls=True,
                            can_send_other_messages=True, can_add_web_page_previews=True)
    await update.effective_chat.restrict_member(user_id, perms)
    await update.message.reply_text(f"🔊 <b>{name}</b> has been unmuted.", parse_mode="HTML")

# --- Filters ---

async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /filter <keyword> <response>"); return
    keyword = context.args[0].lower()
    response = " ".join(context.args[1:])
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO chat_filters VALUES (?, ?, ?)", (update.effective_chat.id, keyword, response))
    conn.commit(); conn.close()
    await update.message.reply_text(f"✅ Filter added for: <code>{keyword}</code>", parse_mode="HTML")

async def remove_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: /stop <keyword>"); return
    keyword = context.args[0].lower()
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_filters WHERE chat_id = ? AND keyword = ?", (update.effective_chat.id, keyword))
    deleted = cursor.rowcount
    conn.commit(); conn.close()
    if deleted:
        await update.message.reply_text(f"✅ Filter for <code>{keyword}</code> removed.", parse_mode="HTML")
    else:
        await update.message.reply_text(f"⚠️ No filter found for <code>{keyword}</code>.", parse_mode="HTML")

async def list_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT keyword FROM chat_filters WHERE chat_id = ?", (update.effective_chat.id,))
    rows = cursor.fetchall(); conn.close()
    if not rows:
        await update.message.reply_text("No filters set in this chat."); return
    lines = "\n".join(f"• <code>{r[0]}</code>" for r in rows)
    await update.message.reply_text(f"🔍 <b>Active filters:</b>\n{lines}", parse_mode="HTML")

# --- Admin Commands ---

async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to pin it."); return
    await update.message.reply_to_message.pin()
    await update.message.reply_text("📌 Message pinned.")

async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    await update.effective_chat.unpin_message()
    await update.message.reply_text("📌 Message unpinned.")

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: /setrules <rules text>"); return
    rules = " ".join(context.args)
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO chat_rules VALUES (?, ?)", (update.effective_chat.id, rules))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ Rules updated!")

async def get_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('novapump_memory.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT rules FROM chat_rules WHERE chat_id = ?", (update.effective_chat.id,))
    row = cursor.fetchone(); conn.close()
    if not row:
        await update.message.reply_text("No rules have been set for this chat."); return
    await update.message.reply_text(f"📜 <b>Rules:</b>\n\n{row[0]}", parse_mode="HTML")

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    user_id, name = get_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a user or provide their ID to promote."); return
    await update.effective_chat.promote_member(user_id, can_manage_chat=True, can_delete_messages=True,
                                               can_restrict_members=True, can_pin_messages=True)
    await update.message.reply_text(f"⬆️ <b>{name}</b> has been promoted to admin.", parse_mode="HTML")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context): return
    user_id, name = get_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a user or provide their ID to demote."); return
    await update.effective_chat.promote_member(user_id)
    await update.message.reply_text(f"⬇️ <b>{name}</b> has been demoted.", parse_mode="HTML")

async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await update.effective_chat.get_administrators()
    lines = []
    for a in admins:
        tag = " 👑" if a.status == ChatMemberStatus.OWNER else ""
        lines.append(f"• {a.user.full_name}{tag}")
    await update.message.reply_text("🛡 <b>Admins in this chat:</b>\n" + "\n".join(lines), parse_mode="HTML")

async def help_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 <b>Group Management Commands</b>\n\n"
        "<b>👋 Welcome/Goodbye</b>\n"
        "/setwelcome &lt;msg&gt; — Set welcome message\n"
        "/setgoodbye &lt;msg&gt; — Set goodbye message\n"
        "/resetwelcome — Reset welcome to default\n"
        "Placeholders: {name} {username} {chat} {id}\n\n"
        "<b>🚫 Moderation</b>\n"
        "/ban [reply/ID] [reason] — Ban a user\n"
        "/unban [reply/ID] — Unban a user\n"
        "/kick [reply/ID] [reason] — Kick a user\n"
        "/mute [reply/ID] [10m/1h/1d] — Mute a user\n"
        "/unmute [reply/ID] — Unmute a user\n\n"
        "<b>🔍 Filters</b>\n"
        "/filter &lt;keyword&gt; &lt;response&gt; — Add auto-reply\n"
        "/stop &lt;keyword&gt; — Remove a filter\n"
        "/filters — List all filters\n\n"
        "<b>🛡 Admin</b>\n"
        "/promote [reply/ID] — Promote to admin\n"
        "/demote [reply/ID] — Demote from admin\n"
        "/adminlist — List all admins\n"
        "/pin — Pin replied message\n"
        "/unpin — Unpin last pinned message\n"
        "/setrules &lt;text&gt; — Set group rules\n"
        "/rules — Show group rules\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    init_db()
    keep_alive()
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Add /start command and text message handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # --- Group management handlers ---
    bot_app.add_handler(ChatMemberHandler(on_member_update, ChatMemberHandler.CHAT_MEMBER))
    bot_app.add_handler(CommandHandler("setwelcome", set_welcome))
    bot_app.add_handler(CommandHandler("setgoodbye", set_goodbye))
    bot_app.add_handler(CommandHandler("resetwelcome", reset_welcome))
    bot_app.add_handler(CommandHandler("ban", ban))
    bot_app.add_handler(CommandHandler("unban", unban))
    bot_app.add_handler(CommandHandler("kick", kick))
    bot_app.add_handler(CommandHandler("mute", mute))
    bot_app.add_handler(CommandHandler("unmute", unmute))
    bot_app.add_handler(CommandHandler("filter", add_filter))
    bot_app.add_handler(CommandHandler("stop", remove_filter))
    bot_app.add_handler(CommandHandler("filters", list_filters))
    bot_app.add_handler(CommandHandler("promote", promote))
    bot_app.add_handler(CommandHandler("demote", demote))
    bot_app.add_handler(CommandHandler("adminlist", adminlist))
    bot_app.add_handler(CommandHandler("pin", pin))
    bot_app.add_handler(CommandHandler("unpin", unpin))
    bot_app.add_handler(CommandHandler("setrules", set_rules))
    bot_app.add_handler(CommandHandler("rules", get_rules))
    bot_app.add_handler(CommandHandler("grouphelp", help_group))
    
    print("NovaPump is live and remembers everything...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)
