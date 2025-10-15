import os
import random
import hashlib
from datetime import datetime, date
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler
from config import BOT_TOKEN, DATABASE_URL, GROUP_CHAT_ID
from db import init_db
import sys
import asyncio

# === INIT ===
init_db()

# Ensure required columns exist (safe: uses IF NOT EXISTS)
def ensure_columns():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS user_id BIGINT;
    """)
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS username TEXT;
    """)
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS first_name TEXT;
    """)
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS birthday DATE;
    """)
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS last_sent DATE;
    """)
    conn.commit()
    cur.close()
    conn.close()

ensure_columns()

# Validate token
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set. Please add it to your environment or .env file.")
    sys.exit(1)

# Convert GROUP_CHAT_ID to int if possible
if GROUP_CHAT_ID:
    try:
        GROUP_CHAT_ID = int(GROUP_CHAT_ID)
    except ValueError:
        print("WARNING: GROUP_CHAT_ID is not numeric. Telegram allows string chat IDs.")

# === DATABASE CONNECTION ===
def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# === BIBLE VERSES & MESSAGE TEMPLATES ===
VERSES = [
    "Psalm 20:4 – May He give you the desire of your heart and make all your plans succeed.",
    "Jeremiah 29:11 – 'For I know the plans I have for you,' declares the LORD.",
    "Numbers 6:24 – The LORD bless you and keep you.",
    "Proverbs 9:11 – For through wisdom your days will be many.",
    "Psalm 37:4 – Delight yourself in the Lord, and He will give you the desires of your heart."
]

MESSAGES = [
    "🎉 Happy Birthday, {name}! May your heart overflow with joy and gratitude today. 💖 {verse}",
    "🎂 Wishing you a blessed birthday, {name}! May God’s grace shine upon you this year. 🙏 {verse}",
    "🎊 Celebrate your day, {name}! May your faith and joy grow stronger each year. 🌟 {verse}",
    "🎁 Happy Birthday, {name}! You are fearfully and wonderfully made. 💕 {verse}",
    "🌼 Blessings to you, {name}! May this year bring peace, favor, and divine purpose. ✨ {verse}"
]

# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        "👋 Hello! I’m your Birthday Blessing Bot.\n\n"
        "Commands:\n"
        "/addbirthday YYYY-MM-DD [name] [username] – Add or update a birthday 🎂\n"
        "/mybirthday – See your birthday 📅\n"
        "/listbirthdays – View all registered birthdays 👥\n"
        "/testbirthdays – Test sending today's birthday messages manually 🧪\n\n"
        "You can now add birthdays for others by providing their name and username."
    )

async def add_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    if not context.args:
        await update.message.reply_text("⚠️ Please use: /addbirthday YYYY-MM-DD [name] [username]")
        return

    try:
        date_str = context.args[0]
        birthday_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # Optional name and username
        name = context.args[1] if len(context.args) > 1 else update.message.from_user.first_name
        username = context.args[2].lstrip("@") if len(context.args) > 2 else update.message.from_user.username

        # Determine user_id
        if len(context.args) > 2:
            # Generate a stable pseudo-ID from username (same hash for same user)
            user_id = int(hashlib.sha256(username.encode()).hexdigest(), 16) % (10**10)
        else:
            # Use actual Telegram user ID
            user_id = update.message.from_user.id

        # Insert or update
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (user_id, username, first_name, birthday)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET birthday = EXCLUDED.birthday,
                              first_name = EXCLUDED.first_name,
                              username = EXCLUDED.username;
            """, (user_id, username, name, date_str))
            conn.commit()

        await update.message.reply_text(f"✅ Birthday for {name} ({date_str}) has been saved!")

        # Immediate check if birthday is today
        if birthday_date == date.today():
            await send_birthday_message(context.application, {
                'user_id': user_id,
                'username': username,
                'first_name': name
            })

    except ValueError:
        await update.message.reply_text("⚠️ Invalid date format. Use YYYY-MM-DD.")

async def my_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user = update.message.from_user
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT birthday FROM users WHERE user_id=%s", (user.id,))
        result = cur.fetchone()
    if result and result.get('birthday'):
        await update.message.reply_text(f"📅 Your registered birthday: {result['birthday']}")
    else:
        await update.message.reply_text("❌ You haven’t registered your birthday yet.\nUse /addbirthday YYYY-MM-DD")

async def list_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT first_name, username, birthday FROM users ORDER BY birthday;")
        people = cur.fetchall()
    if not people:
        await update.message.reply_text("No birthdays registered yet 🎂")
        return
    msg = "🎉 *Birthday List:*\n\n"
    for p in people:
        uname = f"@{p.get('username')}" if p.get('username') else p.get('first_name') or "Unknown"
        msg += f"🎂 {p.get('first_name') or uname} ({uname}) – {p.get('birthday')}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# === BIRTHDAY CHECK FUNCTION ===
async def send_birthday_message(app, user):
    # Use user_id for last_sent checks and updates
    user_id = user.get('user_id')
    today = date.today()
    with get_conn() as conn:
        cur = conn.cursor()
        if user_id is not None:
            cur.execute("SELECT last_sent FROM users WHERE user_id=%s", (user_id,))
        else:
            # Fallback to first_name+username if user_id missing
            cur.execute("SELECT last_sent FROM users WHERE first_name=%s AND username=%s", (user.get('first_name'), user.get('username')))
        result = cur.fetchone()
        if result and result.get('last_sent') == today:
            return

    verse = random.choice(VERSES)
    text_template = random.choice(MESSAGES)
    name_tag = f"{user.get('first_name')} (@{user.get('username')})" if user.get('username') else user.get('first_name') or "Friend"

    msg = (
        f"╔════════════════╗╔════════════════╗╔════════════════╗\n"
        f"🎉 *Happy Birthday, {name_tag}!* 🎉\n"
        f"May your day be filled with joy, love, and laughter 💖\n"
        f"📖 {verse}\n"
        f"🎁 Wishing you an amazing year ahead! ✨\n"
        f"🍰🎂🎉 HBD {name_tag}! 🎉🎂🍰\n"
        f"╚════════════════╝╚════════════════╝╚════════════════╝"
    )

    try:
        await app.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode="Markdown")
        print(f"✅ Sent birthday message for {name_tag}")
        with get_conn() as conn:
            cur = conn.cursor()
            if user_id is not None:
                cur.execute("UPDATE users SET last_sent=%s WHERE user_id=%s", (today, user_id))
            else:
                cur.execute("UPDATE users SET last_sent=%s WHERE first_name=%s AND username=%s", (today, user.get('first_name'), user.get('username')))
            conn.commit()
    except Exception as e:
        print(f"❌ Error sending birthday message for {name_tag}: {e}")

async def check_birthdays(app):
    today_str = datetime.now().strftime("%m-%d")
    with get_conn() as conn:
        cur = conn.cursor()
        # Select user_id, first_name, username to prefer user_id usage
        cur.execute("SELECT user_id, first_name, username FROM users WHERE to_char(birthday, 'MM-DD')=%s", (today_str,))
        people = cur.fetchall()
    for user in people:
        # Ensure we have dict-like access
        await send_birthday_message(app, user)

# === MANUAL TEST COMMAND ===
async def test_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await check_birthdays(context.application)
    await update.message.reply_text("✅ Test birthday check triggered!")

# === MAIN FUNCTION ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addbirthday", add_birthday))
    app.add_handler(CommandHandler("mybirthday", my_birthday))
    app.add_handler(CommandHandler("listbirthdays", list_birthdays))
    app.add_handler(CommandHandler("testbirthdays", test_birthday))

    # Scheduler for multiple checks (8 AM, 12 PM, 4 PM, 8 PM)
    scheduler = BackgroundScheduler()
    for hour in [8, 12, 16, 20]:
        scheduler.add_job(lambda: app.create_task(check_birthdays(app)), 'cron', hour=hour)
    scheduler.start()

    # Run once at startup
    async def on_startup(app):
        print("🧪 Running startup birthday check...")
        await check_birthdays(app)
        print("✅ Startup birthday check complete.")

    app.post_init = on_startup

    print("🚀 Birthday Blessing Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()