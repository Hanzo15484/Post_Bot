from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from db_handler import db

# Flag that tells when user is adding a channel
ADDCH_FLAG = "add_channel_mode"


# -----------------------------------------------------------
# /addch — Begin channel adding process
# -----------------------------------------------------------
async def addch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[ADDCH_FLAG] = True

    await update.message.reply_text(
        "🌸 Please forward **any message from the channel** you want to add.\n"
        "Make sure I am an **admin** in that channel."
    )


# -----------------------------------------------------------
# Detect forwarded channel & save it
# -----------------------------------------------------------
async def addch_forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    # If user is NOT in add-channel mode, ignore silently
    if not context.user_data.get(ADDCH_FLAG):
        return False  # do NOT block other modules

    print("ADDCH FORWARD TRIGGERED")

    user_id = update.effective_user.id
    if not msg:
        return False

    # -------- detect channel forwarded message safely --------
    origin = getattr(msg, "forward_from_chat", None)

    if not origin:
        fo = getattr(msg, "forward_origin", None)
        if fo:
            origin = getattr(fo, "chat", None)

    if not origin:
        await msg.reply_text("❌ This does not look like a channel forward.")
        return False

    if origin.type != "channel":
        await msg.reply_text("❌ Please forward from a **channel only**.")
        return False

    channel_id = origin.id
    channel_title = origin.title or "Unknown Channel"

    # -------- bot must be admin --------
    try:
        member = await context.bot.get_chat_member(channel_id, context.bot.id)
        if member.status not in ("administrator", "creator"):
            await msg.reply_text("❌ I am not admin in that channel.")
            return False
    except:
        await msg.reply_text("❌ I cannot access that channel. Add me as admin.")
        return False

    # -------- save to DB --------
    db.query(
        "INSERT OR REPLACE INTO channels (channel_id, channel_title, owner_id) VALUES (?, ?, ?)",
        (channel_id, channel_title, user_id)
    )

    # turn OFF add-channel mode
    context.user_data[ADDCH_FLAG] = False
    print("ADDCH DISABLED")

    await msg.reply_text(
        f"🌸 Channel Added Successfully!\n\n"
        f"**{channel_title}**\n"
        f"`{channel_id}`",
        parse_mode="Markdown"
    )

    return False  # do NOT block post handlers


# -----------------------------------------------------------
# /mychannels — list user channels
# -----------------------------------------------------------
async def mychannels_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    rows = db.query(
        "SELECT channel_id, channel_title FROM channels WHERE owner_id = ?",
        (user_id,), fetch=True
    )

    if not rows:
        await update.message.reply_text("🌸 You have no saved channels.")
        return

    text = "📚 **Your Channels:**\n\n"
    for cid, title in rows:
        text += f"• **{title}** — `{cid}`\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# -----------------------------------------------------------
# /delch — show delete options
# -----------------------------------------------------------
async def delch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    rows = db.query(
        "SELECT channel_id, channel_title FROM channels WHERE owner_id = ?",
        (user_id,), fetch=True
    )

    if not rows:
        await update.message.reply_text("❌ No channels to delete.")
        return

    keyboard = []
    row = []

    for i, (cid, title) in enumerate(rows):
        row.append(InlineKeyboardButton(title, callback_data=f"delch_{cid}"))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="delch_cancel")])

    await update.message.reply_text(
        "🗑 Select a channel to delete:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# -----------------------------------------------------------
# Handle delete callback
# -----------------------------------------------------------
async def delch_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "delch_cancel":
        await query.message.delete()
        return

    if data.startswith("delch_"):
        channel_id = int(data.split("_")[1])
        db.query("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        await query.edit_message_text("🗑 Channel deleted successfully!")
        return


# -----------------------------------------------------------
# Handler export for main.py
# -----------------------------------------------------------
def addch_module():
    return [
        (CommandHandler("addch", addch_handler), 0),
        (CommandHandler("mychannels", mychannels_handler), 0),
        (CommandHandler("delch", delch_handler), 0),

        (CallbackQueryHandler(delch_button, pattern="^delch_"), 1),
        (CallbackQueryHandler(delch_button, pattern="delch_cancel"), 1),

        # IMPORTANT: addch forward handler MUST be non-blocking
        (MessageHandler(~filters.COMMAND, addch_forward_handler, block=False), 3),
    ]
