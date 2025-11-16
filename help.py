from telegram import Update
from telegram.ext import ContextTypes
from db_handler import db

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🌸 **Bot Commands:**\n\n"
        "**Channel Controls:**\n"
        "/addch - Add channel\n"
        "/delch - Delete channel\n"
        "/mychannels - View channels\n\n"
        "**Posting System:**\n"
        "/post - Create/Edit channel posts\n\n"
        "**Admin Panel:**\n"
        "/adminpanel - Manage bot settings\n"
        "/addadmin - Promote user\n"
        "/removeadmin - Demote admin\n\n"
        "**Misc:**\n"
        "/alive - Check bot status\n"
        "/help - Show this help\n"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


async def help_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Use /help to get the command list.")
