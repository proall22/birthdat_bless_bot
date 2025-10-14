import os
import random
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

# Ensure last_sent column exists
def ensure_last_sent_column():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS last_sent DATE;
    """)
    conn.commit()
    cur.close()
    conn.close()

ensure_last_sent_column()

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
        username = context.args[2] if len(context.args) > 2 else update.message.from_user.username

        # Always assign a valid user_id
        if len(context.args) <= 2:
            user_id = update.message.from_user.id
        else:
            # unique positive integer for other users
            user_id = int(datetime.now().timestamp() * 1000)

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

        # Check immediately if birthday is today
        if birthday_date == date.today():
            await send_birthday_message(context.application, {'user_id': user_id, 'username': username, 'first_name': name})

    except ValueError:
        await update.message.reply_text("⚠️ Invalid date format. Use YYYY-MM-DD.")

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
        username = context.args[2] if len(context.args) > 2 else update.message.from_user.username

        # Assign user_id: real user_id for self, negative unique ID for others
        user_id = update.message.from_user.id if len(context.args) <= 2 else -int(datetime.now().timestamp())

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
            await send_birthday_message(context.application, {'user_id': user_id, 'username': username, 'first_name': name})

    except ValueError:
        await update.message.reply_text("⚠️ Invalid date format. Use YYYY-MM-DD.")

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
        username = context.args[2] if len(context.args) > 2 else update.message.from_user.username
        user_id = update.message.from_user.id if len(context.args) <= 2 else None

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
            await send_birthday_message(context.application, {'user_id': user_id, 'username': username, 'first_name': name})

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
    if result and result['birthday']:
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
        uname = f"@{p['username']}" if p['username'] else p['first_name']
        msg += f"🎂 {p['first_name']} ({uname}) – {p['birthday']}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# === BIRTHDAY CHECK FUNCTION ===
async def send_birthday_message(app, user):
    today = date.today()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT last_sent FROM users WHERE first_name=%s AND username=%s", (user['first_name'], user.get('username')))
        result = cur.fetchone()
        if result and result['last_sent'] == today:
            return

    verse = random.choice(VERSES)
    text_template = random.choice(MESSAGES)
    name_tag = f"{user['first_name']} (@{user['username']})" if user.get('username') else user['first_name']

    msg = (
        f"╔════════════════╗\n"
        f"🎉 *Happy Birthday, {name_tag}!* 🎉\n"
        f"May your day be filled with joy, love, and laughter 💖\n"
        f"📖 {verse}\n"
        f"🎁 Wishing you an amazing year ahead! ✨\n"
        f"🍰🎂🎉 HBD {name_tag}! 🎉🎂🍰\n"
        f"╚════════════════╝"
    )

    try:
        await app.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode="Markdown")
        print(f"✅ Sent birthday message for {name_tag}")
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET last_sent=%s WHERE first_name=%s AND username=%s", (today, user['first_name'], user.get('username')))
            conn.commit()
    except Exception as e:
        print(f"❌ Error sending birthday message for {name_tag}: {e}")

async def check_birthdays(app):
    today_str = datetime.now().strftime("%m-%d")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT first_name, username, user_id FROM users WHERE to_char(birthday, 'MM-DD')=%s", (today_str,))
        people = cur.fetchall()
    for user in people:
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
