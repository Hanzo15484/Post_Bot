# main.py
import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Local modules (make sure these files exist in the same folder)
import init_db
from db_handler import db
from start import start_handler, start_button_handler
from help import help_handler, help_button_handler
from admin import adminpanel_handler, is_limited, get_uptime  # get_uptime optional
from addch import addch_module
from post import post_module

# -------------------------
# Configuration
# -------------------------
OWNER_ID = 5373577888
ENV_FILE = "Bot_Token.env"

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# -------------------------
# Utility: load token
# -------------------------
def load_token(env_path: str = ENV_FILE) -> str:
    load_dotenv(env_path)
    token = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("Bot token not found in %s or environment variables.", env_path)
        raise SystemExit("Bot token not found. Put BOT_TOKEN=<token> in Bot_Token.env")
    if ":" not in token:
        logger.error("Invalid token format (missing ':').")
        raise SystemExit("Invalid bot token format.")
    return token


# -------------------------
# Small DB helper commands (admin management)
# -------------------------
async def addadmin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promote a user to admin (OWNER only). Usage: /addadmin <user_id>"""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Only the owner can use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return

    try:
        uid = int(context.args[0])
    except:
        await update.message.reply_text("Invalid user id.")
        return

    # Insert or update user as admin
    db.query(
        "INSERT OR IGNORE INTO users (user_id, is_admin) VALUES (?, ?)",
        (uid, 1),
    )
    db.query("UPDATE users SET is_admin = 1 WHERE user_id = ?", (uid,))
    await update.message.reply_text(f"✅ User `{uid}` promoted to admin.", parse_mode="Markdown")
    logger.info("Owner promoted %s to admin.", uid)


async def removeadmin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demote an admin (OWNER only). Usage: /removeadmin <user_id>"""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Only the owner can use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return

    try:
        uid = int(context.args[0])
    except:
        await update.message.reply_text("Invalid user id.")
        return

    db.query("UPDATE users SET is_admin = 0 WHERE user_id = ?", (uid,))
    await update.message.reply_text(f"✅ User `{uid}` demoted from admin.", parse_mode="Markdown")
    logger.info("Owner demoted %s from admin.", uid)


# -------------------------
# Simple alive / stats
# -------------------------
async def alive_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 I'm alive and ready 😊")


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Rate-limit small queries by user (prevent spam)
    user_id = update.effective_user.id
    if is_limited(user_id):
        await update.message.reply_text("⏳ Please wait a moment before requesting again.")
        return

    users_count = db.query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
    admins_count = db.query("SELECT COUNT(*) FROM users WHERE is_admin = 1", fetch=True)[0][0]
    channels_count = db.query("SELECT COUNT(*) FROM channels", fetch=True)[0][0]
    uptime = get_uptime() if "get_uptime" in globals() else "N/A"

    text = (
        f"📊 Stats:\n\n"
        f"• Users: {users_count}\n"
        f"• Admins: {admins_count}\n"
        f"• Channels: {channels_count}\n"
        f"• Uptime: {uptime}\n"
    )
    await update.message.reply_text(text)


# -------------------------
# Error handler
# -------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Exception while handling an update: %s", context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("⚠️ An error occurred while processing your request.")
    except Exception:
        logger.exception("Failed to notify user about the exception.")


# -------------------------
# Register handlers helper
# -------------------------
def register_handlers(app: Application):
    # Basic commands
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(start_button_handler, pattern="^start_"))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CallbackQueryHandler(help_button_handler, pattern="^help_"))
    app.add_handler(CommandHandler("alive", alive_handler))
    app.add_handler(CommandHandler("stats", stats_handler))

    # Admin commands
    app.add_handler(CommandHandler("adminpanel", adminpanel_handler))
    app.add_handler(CommandHandler("addadmin", addadmin_handler))
    app.add_handler(CommandHandler("removeadmin", removeadmin_handler))

    # Modules: addch and post (they return handler lists)
    for h in addch_module():
        app.add_handler(h)

    for h in post_module():
        app.add_handler(h)

    # Allow modules' message handlers to run in proper order:
    # - Group numbers can be used when adding handlers via app.add_handler(handler, group=N)
    # If you need strict order, add handlers with explicit group numbers where needed.

    # Global catch-all (non-command messages) - lightweight no-op to keep event loop flowing
    app.add_handler(MessageHandler(filters.COMMAND, lambda u, c: None))


# -------------------------
# Entrypoint
# -------------------------
def main():
    # create / migrate DB
    init_db.setup_db()

    # load token
    TOKEN = load_token()

    # prepare executor for blocking tasks (SQLite, file I/O)
    max_workers = int(os.getenv("BOT_THREAD_WORKERS", "8"))
    executor = ThreadPoolExecutor(max_workers=max_workers)
    loop = asyncio.get_event_loop()
    loop.set_default_executor(executor)

    # Build application
    app = (
        Application.builder()
        .token(TOKEN)
        .read_timeout(15)
        .write_timeout(15)
        .connect_timeout(10)
        .pool_timeout(10)
        .concurrent_updates(True)
        .build()
    )

    # Register handlers
    register_handlers(app)

    # Error handler
    app.add_error_handler(error_handler)

    # Print helpful startup info
    logger.info("Starting bot...")
    try:
        me = app.bot.get_me()
        logger.info("Bot: %s (@%s) id=%s", me.first_name, me.username, me.id)
    except Exception as e:
        logger.warning("Could not fetch bot info: %s", e)

    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception("Exception in run_polling: %s", e)
    finally:
        executor.shutdown(wait=True)
        logger.info("Executor shutdown complete.")


if __name__ == "__main__":
    main()
