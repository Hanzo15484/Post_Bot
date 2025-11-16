from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db_handler import db

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Save user in DB
    db.query(
        "INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
        (user.id, user.first_name, user.username)
    )

    keyboard = [
        [InlineKeyboardButton("📢 Add Channel", callback_data="start_addch")],
        [InlineKeyboardButton("📝 Post", callback_data="start_post")],
        [InlineKeyboardButton("❓ Help", callback_data="start_help")]
    ]

    await update.message.reply_text(
        f"🌸 Welcome {user.first_name}!\n\nI can help you post & edit messages in your channels.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def start_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "start_addch":
        await query.edit_message_text("Use /addch to add a channel.")
    elif query.data == "start_post":
        await query.edit_message_text("Use /post to start posting.")
    else:
        await query.edit_message_text("Use /help to see all commands.")
