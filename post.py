import math
import re
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from db_handler import db

OWNER_ID = 5373577888

USER_SESSION = {}  # Per-user session
PAGE_SIZE = 12     # 4 columns × 3 rows = 12 channels per page


# ----------------------------------------------------------
# /post → Only Owner Allowed
# ----------------------------------------------------------
async def post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != OWNER_ID:
        await update.message.reply_text("❌ You are not allowed to use this command.")
        return

    session = USER_SESSION.setdefault(user_id, {})
    session["step"] = "select_channel"
    session["page"] = 0

    await send_channel_page(update, context, user_id)


# ----------------------------------------------------------
# Send Channel List Page
# ----------------------------------------------------------
async def send_channel_page(update_or_query, context, user_id):
    session = USER_SESSION[user_id]
    page = session["page"]

    rows = db.query(
        "SELECT channel_id, channel_title FROM channels WHERE owner_id = ?",
        (user_id,), fetch=True
    )

    if not rows:
        await update_or_query.message.reply_text("❌ No channels saved. Add one using /addch.")
        return

    total_pages = math.ceil(len(rows) / PAGE_SIZE)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_channels = rows[start:end]

    keyboard = []
    row = []

    for i, (cid, title) in enumerate(page_channels):
        row.append(InlineKeyboardButton(title, callback_data=f"post_ch_{cid}"))
        if (i + 1) % 4 == 0:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅ Back", callback_data="page_back"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡", callback_data="page_next"))

    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="post_close")])

    text = f"📢 Select a channel (Page {page+1}/{total_pages}):"

    if hasattr(update_or_query, "message"):
        await update_or_query.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update_or_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ----------------------------------------------------------
# Handle pagination + channel selection + Post/Edit menu
# ----------------------------------------------------------
async def post_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    await query.answer()

    if user_id != OWNER_ID:
        await query.edit_message_text("❌ You are not allowed to use this.")
        return

    session = USER_SESSION.setdefault(user_id, {})

    # -------- Pagination -------- #
    if data == "page_next":
        session["page"] += 1
        await send_channel_page(query, context, user_id)
        return

    if data == "page_back":
        session["page"] -= 1
        await send_channel_page(query, context, user_id)
        return

    # -------- Close -------- #
    if data == "post_close":
        await query.message.delete()
        return

    # -------- Show POST / EDIT options -------- #
    if data.startswith("post_ch_"):
        channel_id = int(data.split("_")[2])

        row = db.query(
            "SELECT channel_title FROM channels WHERE channel_id = ?",
            (channel_id,), fetch=True
        )

        if not row:
            await query.edit_message_text("❌ Channel not found.")
            return

        title = row[0][0]

        kb = [
            [
                InlineKeyboardButton("📨 Post", callback_data=f"post_do_{channel_id}"),
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit_do_{channel_id}")
            ],
            [InlineKeyboardButton("❌ Close", callback_data="post_close")]
        ]

        await query.edit_message_text(
            f"Selected Channel:\n\n**{title}**\n`{channel_id}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # ----------------------------------------------------------
    # Start POST mode
    # ----------------------------------------------------------
    if data.startswith("post_do_"):
        channel_id = int(data.split("_")[2])

        title = db.query(
            "SELECT channel_title FROM channels WHERE channel_id = ?",
            (channel_id,), fetch=True
        )[0][0]

        USER_SESSION[user_id] = {
            "step": "await_message",
            "mode": "post",
            "channel_id": channel_id,
            "channel_title": title,
            "message": None,
            "edit_target": None,
            "buttons": [],
            "page": session.get("page", 0)
        }

        await query.edit_message_text(
            f"🌸 Send or forward the **message to post** in:\n**{title}**",
            parse_mode="Markdown"
        )
        return

    # ----------------------------------------------------------
    # Start EDIT mode
    # ----------------------------------------------------------
    if data.startswith("edit_do_"):
        channel_id = int(data.split("_")[2])

        title = db.query(
            "SELECT channel_title FROM channels WHERE channel_id = ?",
            (channel_id,), fetch=True
        )[0][0]

        USER_SESSION[user_id] = {
            "step": "await_edit_forward",
            "mode": "edit",
            "channel_id": channel_id,
            "channel_title": title,
            "message": None,
            "edit_target": None,
            "buttons": [],
            "page": session.get("page", 0)
        }

        await query.edit_message_text(
            f"✏️ Forward the **original message from {title}** to edit.",
            parse_mode="Markdown"
        )
        return


# ----------------------------------------------------------
# Handle User Messages (Forwarded / New content)
# ----------------------------------------------------------
async def user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return

    if user_id not in USER_SESSION:
        return

    session = USER_SESSION[user_id]

    # -------------- EDIT MODE: Forward original message -------------- #
    if session["step"] == "await_edit_forward":
        if not update.message.forward_from_chat:
            await update.message.reply_text("❌ Forward original channel message.")
            return

        fwd_chat = update.message.forward_from_chat.id
        fwd_msg_id = update.message.forward_from_message_id

        if fwd_chat != session["channel_id"]:
            await update.message.reply_text("❌ Not from the selected channel.")
            return

        session["edit_target"] = fwd_msg_id
        session["step"] = "await_edit_newcontent"

        await update.message.reply_text("✏️ Now send the **new edited content**.")
        return

    # -------------- EDIT MODE: new content received -------------- #
    if session["step"] == "await_edit_newcontent":
        session["message"] = update.message
        session["step"] = "add_button_q"

        kb = [
            [
                InlineKeyboardButton("Yes", callback_data="addbtn_yes"),
                InlineKeyboardButton("No", callback_data="addbtn_no")
            ]
        ]

        await update.message.reply_text(
            "Would you like to add button?",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # -------------- POST MODE: message received -------------- #
    if session["step"] == "await_message":
        session["message"] = update.message
        session["step"] = "add_button_q"

        kb = [
            [
                InlineKeyboardButton("Yes", callback_data="addbtn_yes"),
                InlineKeyboardButton("No", callback_data="addbtn_no")
            ]
        ]

        await update.message.reply_text(
            "Would you like to add button?",
            reply_markup=InlineKeyboardMarkup(kb)
        )


# ----------------------------------------------------------
# Button Flow (YES/NO/Add More/Continue)
# ----------------------------------------------------------
async def post_button_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    await query.answer()

    if user_id != OWNER_ID:
        return

    if user_id not in USER_SESSION:
        return

    session = USER_SESSION[user_id]

    msg = session["message"]
    buttons = session["buttons"]
    markup = InlineKeyboardMarkup(buttons) if buttons else None

    # Show URL button input mode
    if data == "addbtn_yes":
        session["step"] = "await_button_format"
        await query.edit_message_text(
            "Send button in format:\n\n"
            "`Text - URL`\n"
            "`Text - URL:same` (same row)\n"
            "`Text - PopMessage:alert:True` (popup alert)`",
            parse_mode="Markdown"
        )
        return

    # No button → Ask send post?
    if data == "addbtn_no":
        session["step"] = "send_post_q"

        kb = [
            [
                InlineKeyboardButton("Yes", callback_data="sendpost_yes"),
                InlineKeyboardButton("No", callback_data="sendpost_no")
            ]
        ]

        await query.edit_message_text(
            "Would you like to send the post?",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # ----------------------------------------------------------
    # SEND POST — final step
    # ----------------------------------------------------------
    if data == "sendpost_yes":

        # ---------------- EDIT MODE ---------------- #
        if session["mode"] == "edit":
            try:
                if msg.text or msg.caption:
                    await context.bot.edit_message_text(
                        chat_id=session["channel_id"],
                        message_id=session["edit_target"],
                        text=msg.text_html or msg.text,
                        reply_markup=markup
                    )
                elif msg.photo:
                    await context.bot.edit_message_media(
                        chat_id=session["channel_id"],
                        message_id=session["edit_target"],
                        media=InputMediaPhoto(msg.photo[-1].file_id),
                        reply_markup=markup
                    )
                elif msg.video:
                    await context.bot.edit_message_media(
                        chat_id=session["channel_id"],
                        message_id=session["edit_target"],
                        media=InputMediaVideo(msg.video.file_id),
                        reply_markup=markup
                    )

                await query.edit_message_text("✨ Message Edited Successfully!")
            except Exception as e:
                await query.edit_message_text(f"❌ Failed: `{e}`")

            USER_SESSION.pop(user_id, None)
            return

        # ---------------- POST MODE ---------------- #
        if session["mode"] == "post":
            try:
                if msg.photo:
                    await context.bot.send_photo(
                        session["channel_id"],
                        msg.photo[-1].file_id,
                        caption=msg.caption or "",
                        reply_markup=markup
                    )
                elif msg.video:
                    await context.bot.send_video(
                        session["channel_id"],
                        msg.video.file_id,
                        caption=msg.caption or "",
                        reply_markup=markup
                    )
                else:
                    await context.bot.send_message(
                        session["channel_id"],
                        msg.text_html or msg.text,
                        reply_markup=markup
                    )

                await query.edit_message_text("🌸 Post sent successfully.")
            except Exception as e:
                await query.edit_message_text(f"❌ Failed: `{e}`")

            USER_SESSION.pop(user_id, None)
            return

    # ----------------------------------------------------------
    # NO → ask to send simple message?
    # ----------------------------------------------------------
    if data == "sendpost_no":
        kb = [
            [
                InlineKeyboardButton("Yes", callback_data="sendmsg_yes"),
                InlineKeyboardButton("No", callback_data="sendmsg_no")
            ]
        ]

        await query.edit_message_text(
            "Would you like to send only the message?",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # Send message without buttons
    if data == "sendmsg_yes":
        try:
            if msg.photo:
                await context.bot.send_photo(
                    session["channel_id"], msg.photo[-1].file_id, caption=msg.caption
                )
            elif msg.video:
                await context.bot.send_video(
                    session["channel_id"], msg.video.file_id, caption=msg.caption
                )
            else:
                await context.bot.send_message(
                    session["channel_id"], msg.text
                )

            await query.edit_message_text("🌸 Message sent.")
        except Exception as e:
            await query.edit_message_text(f"❌ Error: `{e}`")

        USER_SESSION.pop(user_id, None)
        return

    # NO → return to button input mode
    if data == "sendmsg_no":
        session["step"] = "await_button_format"
        await query.edit_message_text(
            "Send button in format:\n"
            "`Text - URL`\n"
            "`Text - URL:same`\n"
            "`Text - Pop:alert:True`",
            parse_mode="Markdown"
        )
        return


# ----------------------------------------------------------
# Handle button formatting input
# ----------------------------------------------------------
async def button_format_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return

    if user_id not in USER_SESSION:
        return

    session = USER_SESSION[user_id]
    if session["step"] != "await_button_format":
        return

    text = update.message.text
    btns = session["buttons"]

    # ----------- URL Button ----------- #
    if " - " in text and "alert:" not in text:
        name, url = text.split(" - ", 1)

        button = InlineKeyboardButton(name, url=url.replace(":same", ""))

        if url.endswith(":same") and btns:
            btns[-1].append(button)
        else:
            btns.append([button])

    # ----------- Alert Button ----------- #
    elif ":alert:" in text:
        try:
            name, rest = text.split(" - ", 1)
            msg_alert, val = rest.split(":alert:")
            is_alert = val.strip().lower() == "true"

            cb = f"alert:{msg_alert}:{is_alert}"
            btns.append([InlineKeyboardButton(name, callback_data=cb)])
        except:
            await update.message.reply_text("❌ Invalid format.")
            return

    else:
        await update.message.reply_text("❌ Invalid button format.")
        return

    kb = [
        [
            InlineKeyboardButton("Add More", callback_data="addbtn_yes"),
            InlineKeyboardButton("Continue", callback_data="addbtn_no")
        ]
    ]

    await update.message.reply_text(
        "🌸 Button added.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ----------------------------------------------------------
# EXPORT MODULE
# ----------------------------------------------------------
def post_module():
    return [
        CommandHandler("post", post_handler),
        CallbackQueryHandler(post_button_handler, pattern="^(post_|page_)"),
        CallbackQueryHandler(post_button_flow, pattern="^(addbtn_|sendpost_|sendmsg_)"),
        MessageHandler(~filters.COMMAND, user_message_handler),
        MessageHandler(filters.TEXT, button_format_handler),
  ]
  
