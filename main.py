import os
import random
import hashlib
from datetime import datetime, date
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import BOT_TOKEN, DATABASE_URL, GROUP_CHAT_ID
from db import init_db
import asyncio
from flask import Flask
import threading
import requests
import sys

# === INIT ===
init_db()

# Ensure columns exist safely
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
    print("❌ BOT_TOKEN missing in environment or config.py.")
    sys.exit(1)

# Convert group chat ID
if GROUP_CHAT_ID:
    try:
        GROUP_CHAT_ID = int(GROUP_CHAT_ID)
    except ValueError:
        print("⚠️ GROUP_CHAT_ID is not numeric — using string form.")

# === DATABASE ===
def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# === BIBLE VERSES & TEMPLATES ===
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

# === TELEGRAM COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        "👋 Hello! I’m your Birthday Blessing Bot.\n\n"
        "Commands:\n"
        "/addbirthday YYYY-MM-DD [name] [username] – Add or update a birthday 🎂\n"
        "/mybirthday – See your birthday 📅\n"
        "/listbirthdays – View all birthdays 👥\n"
        "/testbirthdays – Test today's messages manually 🧪"
    )

async def add_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    if not context.args:
        await update.message.reply_text("⚠️ Use: /addbirthday YYYY-MM-DD [name] [username]")
        return
    try:
        date_str = context.args[0]
        birthday_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        name = context.args[1] if len(context.args) > 1 else update.message.from_user.first_name
        username = context.args[2].lstrip("@") if len(context.args) > 2 else update.message.from_user.username
        if len(context.args) > 2:
            user_id = int(hashlib.sha256(username.encode()).hexdigest(), 16) % (10**10)
        else:
            user_id = update.message.from_user.id
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
        await update.message.reply_text(f"✅ Birthday for {name} ({date_str}) saved!")
        today = date.today()
        if birthday_date.month == today.month and birthday_date.day == today.day:
            await send_birthday_message(context.application, {
                'user_id': user_id,
                'username': username,
                'first_name': name
            })
    except ValueError:
        await update.message.reply_text("⚠️ Invalid date. Use YYYY-MM-DD.")

async def my_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user = update.message.from_user
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT birthday FROM users WHERE user_id=%s", (user.id,))
        result = cur.fetchone()
    if result and result.get('birthday'):
        await update.message.reply_text(f"📅 Your birthday: {result['birthday']}")
    else:
        await update.message.reply_text("❌ Not registered yet. Use /addbirthday YYYY-MM-DD")

async def list_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT first_name, username, birthday FROM users ORDER BY birthday;")
        people = cur.fetchall()
    if not people:
        await update.message.reply_text("🎂 No birthdays registered yet.")
        return
    msg = "🎉 *Birthday List:*\n\n"
    for p in people:
        uname = f"@{p.get('username')}" if p.get('username') else p.get('first_name') or "Unknown"
        msg += f"🎂 {p.get('first_name') or uname} ({uname}) – {p.get('birthday')}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# === BIRTHDAY MESSAGE ===
async def send_birthday_message(app, user):
    user_id = user.get('user_id')
    today = date.today()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT last_sent FROM users WHERE user_id=%s", (user_id,))
        result = cur.fetchone()
        if result and result.get('last_sent') == today:
            return
    verse = random.choice(VERSES)
    msg = (
        f"🎉 *Happy Birthday, {user.get('first_name')} (@{user.get('username')})!* 🎉\n"
        f"May your day be filled with joy and blessings 💖\n"
        f"📖 {verse}\n"
        f"🎂 Have an amazing year ahead! ✨"
    )
    try:
        await app.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode="Markdown")
        print(f"✅ Sent birthday message for {user.get('first_name')}")
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET last_sent=%s WHERE user_id=%s", (today, user_id))
            conn.commit()
    except Exception as e:
        print(f"❌ Error sending birthday message: {e}")

async def check_birthdays(app):
    today_str = datetime.now().strftime("%m-%d")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, first_name, username FROM users WHERE to_char(birthday, 'MM-DD')=%s", (today_str,))
        people = cur.fetchall()
    for user in people:
        await send_birthday_message(app, user)

# === TEST COMMAND ===
async def test_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await check_birthdays(context.application)
    await update.message.reply_text("✅ Test birthday check triggered!")

# === KEEP ALIVE ===
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "✅ Birthday Bless Bot is alive!"

def run_flask():
    app_flask.run(host='0.0.0.0', port=8080)

def keep_alive():
    threading.Thread(target=run_flask).start()

async def self_ping(url: str):
    while True:
        try:
            print("🔁 Self-pinging...")
            await asyncio.to_thread(requests.get, url)
        except Exception as e:
            print(f"⚠️ Keep-alive ping failed: {e}")
        await asyncio.sleep(56)

# === PERIODIC CHECK LOOP (Async) ===
async def periodic_birthday_check(app):
    while True:
        try:
            print("🕒 Running periodic birthday check...")
            await check_birthdays(app)
        except Exception as e:
            print(f"⚠️ Error in birthday check loop: {e}")
        await asyncio.sleep(6 * 60 * 60)  # every 6 hours

# === MAIN ===
def main():
    keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addbirthday", add_birthday))
    app.add_handler(CommandHandler("mybirthday", my_birthday))
    app.add_handler(CommandHandler("listbirthdays", list_birthdays))
    app.add_handler(CommandHandler("testbirthdays", test_birthday))

    async def on_startup(app):
        print("🧪 Startup birthday check...")
        await check_birthdays(app)
        base_url = os.getenv("KEEP_ALIVE_URL")
        if base_url:
            asyncio.create_task(self_ping(base_url))
        asyncio.create_task(periodic_birthday_check(app))
        print("✅ Bot fully started.")

    app.post_init = on_startup

    print("🚀 Birthday Bless Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
