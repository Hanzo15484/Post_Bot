from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from db_handler import db

WAITING_ADD_CHANNEL = {}  # Tracks users waiting to add channel


# --------------------- /addch --------------------- #
async def addch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    WAITING_ADD_CHANNEL[user_id] = True

    await update.message.reply_text(
        "🌸 Please **forward a message from your channel**.\n\n"
        "The bot must be an **admin** in that channel."
    )


# ------------ Handle Forwarded Channel Message ------------ #
async def addch_forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user_id = update.effective_user.id

    # Checking if user is in waiting state
    if user_id not in WAITING_ADD_CHANNEL:
        return

    if not msg:
        return

    # --------------------------
    #   SAFE FORWARD DETECTION
    # --------------------------
    origin_chat = None

    # 1) Old-style Telegram forwards
    origin_chat = getattr(msg, "forward_from_chat", None)

    # 2) Some clients send channels via forward_from
    if not origin_chat:
        origin_chat = getattr(msg, "forward_from", None)

    # 3) New API: forward_origin.chat
    if not origin_chat:
        forward_origin = getattr(msg, "forward_origin", None)
        if forward_origin:
            origin_chat = getattr(forward_origin, "chat", None)

    # 4) anonymized forward (only forward_sender_name visible)
    if not origin_chat:
        if getattr(msg, "forward_sender_name", None):
            await msg.reply_text(
                "⚠️ This forwarded message hides the channel identity.\n"
                "Forward a message **directly from the channel**, not anonymized."
            )
            return

        await msg.reply_text("❌ This is not forwarded from a channel.")
        return

    # --------------------------
    # Channel validation
    # --------------------------
    if getattr(origin_chat, "type", "") != "channel":
        await msg.reply_text("❌ Please forward from a **channel only**.")
        return

    channel_id = getattr(origin_chat, "id", None)
    channel_title = getattr(origin_chat, "title", None) or "Unknown Channel"

    if not channel_id:
        await msg.reply_text("❌ Cannot read channel ID. Telegram did not include real channel data.")
        return

    # --------------------------
    # Bot admin check
    # --------------------------
    try:
        bot_status = await context.bot.get_chat_member(channel_id, context.bot.id)
        if bot_status.status not in ["administrator", "creator"]:
            await msg.reply_text(
                "❌ I am **not an admin** in that channel.\n"
                "Please make me admin and try again."
            )
            return
    except Exception:
        await msg.reply_text("❌ I cannot access that channel. Add me to the channel first.")
        return

    # --------------------------
    # Save channel in DB
    # --------------------------
    db.query(
        "INSERT OR REPLACE INTO channels (channel_id, channel_title, owner_id, admin_id) VALUES (?, ?, ?, ?)",
        (channel_id, channel_title, user_id, user_id),
    )

    WAITING_ADD_CHANNEL.pop(user_id, None)

    await msg.reply_text(
        f"🌸 Channel Added Successfully!\n\n"
        f"**{channel_title}**\n"
        f"`{channel_id}`",
        parse_mode="Markdown"
    )


# --------------------- /mychannels --------------------- #
async def mychannels_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    rows = db.query(
        "SELECT channel_id, channel_title FROM channels WHERE owner_id = ?",
        (user_id,), fetch=True
    )

    if not rows:
        await update.message.reply_text("🌸 You have no channels saved.")
        return

    text = "📢 **Your Channels:**\n\n"
    for ch in rows:
        text += f"- {ch[1]} (`{ch[0]}`)\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# --------------------- /delch --------------------- #
async def delch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    rows = db.query(
        "SELECT channel_id, channel_title FROM channels WHERE owner_id = ?",
        (user_id,), fetch=True
    )

    if not rows:
        await update.message.reply_text("❌ No channels to delete.")
        return

    kb = []
    row = []

    for i, (cid, title) in enumerate(rows):
        row.append(InlineKeyboardButton(title, callback_data=f"delch_{cid}"))
        if (i + 1) % 2 == 0:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="delch_cancel")])

    await update.message.reply_text(
        "Select a channel to delete:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def delch_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    await query.answer()

    if data == "delch_cancel":
        await query.message.delete()
        return

    if data.startswith("delch_"):
        cid = int(data.split("_")[1])
        db.query("DELETE FROM channels WHERE channel_id = ?", (cid,))

        await query.edit_message_text("🌸 Channel deleted successfully!")
        return


# Module export
def addch_module():
    return [
        CommandHandler("addch", addch_handler),
        CommandHandler("mychannels", mychannels_handler),
        CommandHandler("delch", delch_handler),
        CallbackQueryHandler(delch_button, pattern="^delch_"),
        CallbackQueryHandler(delch_button, pattern="delch_cancel"),
        MessageHandler(filters.ALL, addch_forward_handler),
                                        ]
