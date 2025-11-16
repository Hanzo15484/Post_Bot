import time
from telegram import Update
from telegram.ext import ContextTypes
from db_handler import db

START_TIME = time.time()

def get_uptime():
    sec = int(time.time() - START_TIME)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}h {m}m {s}s"

RATE_LIMIT = {}
LIMIT_TIME = 3  # seconds

def is_limited(user_id):
    now = time.time()
    if user_id in RATE_LIMIT and now - RATE_LIMIT[user_id] < LIMIT_TIME:
        return True
    RATE_LIMIT[user_id] = now
    return False


async def adminpanel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    row = db.query(
        "SELECT is_admin FROM users WHERE user_id = ?", (user_id,), fetch=True
    )

    if not row or row[0][0] != 1:
        await update.message.reply_text("❌ You are not an admin.")
        return

    uptime = get_uptime()

    text = (
        "🌸 **Admin Panel**\n\n"
        f"**Uptime:** {uptime}\n"
        f"**Admins:** {db.query('SELECT COUNT(*) FROM users WHERE is_admin = 1', fetch=True)[0][0]}\n"
        f"**Users:**  {db.query('SELECT COUNT(*) FROM users', fetch=True)[0][0]}\n\n"
        "Commands:\n"
        "/addadmin <id>\n"
        "/removeadmin <id>\n"
    )

    await update.message.reply_text(text, parse_mode="Markdown")
