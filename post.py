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
from telegram.helpers import escape_markdown
from db_handler import db

OWNER_ID = 5373577888

USER_SESSION = {}  
PAGE_SIZE = 12    


# ----------------------------------------------------------
# Helper: Safe MarkdownV2 Escape
# ----------------------------------------------------------
def md(text: str) -> str:
    if not text:
        return ""
    return escape_markdown(text, version=2)


# ----------------------------------------------------------
# /post command
# ----------------------------------------------------------
async def post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("POST COMMAND TRIGGERED")

    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ You are not allowed to use this command.")
        return

    session = USER_SESSION.setdefault(user_id, {})
    session["step"] = "select_channel"
    session["page"] = 0

    await send_channel_page(update, context, user_id)


# ----------------------------------------------------------
# Send paginated channel list
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
        row.append(
            InlineKeyboardButton(title, callback_data=f"post_ch_{cid}")
        )
        if (i + 1) % 4 == 0:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅ Back", callback_data="page_back"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡", callback_data="page_next"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="post_close")])

    text = f"📢 Select a channel (Page {page+1}/{total_pages}):"

    if hasattr(update_or_query, "message"):
        await update_or_query.message.reply_text(text)
    else:
        await update_or_query.edit_message_text(text)

    await update_or_query.edit_message_reply_markup(
        InlineKeyboardMarkup(keyboard)
    )


# ----------------------------------------------------------
# Handle Buttons
# ----------------------------------------------------------
async def post_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    print("POST BUTTON HANDLER EXECUTED", data)

    await query.answer()

    if user_id != OWNER_ID:
        await query.edit_message_text("❌ You're not allowed.")
        return

    session = USER_SESSION.setdefault(user_id, {})

    # Pagination
    if data == "page_next":
        session["page"] += 1
        await send_channel_page(query, context, user_id)
        return

    if data == "page_back":
        session["page"] -= 1
        await send_channel_page(query, context, user_id)
        return

    # Close
    if data == "post_close":
        await query.message.delete()
        return

    # Select channel
    if data.startswith("post_ch_"):
        channel_id = int(data.split("_")[2])

        res = db.query(
            "SELECT channel_title FROM channels WHERE channel_id = ?",
            (channel_id,), fetch=True
        )

        if not res:
            await query.edit_message_text("❌ Channel not found.")
            return

        title = res[0][0]

        text = (
            f"Selected Channel:\n\n"
            f"*{md(title)}*\n"
            f"`{channel_id}`"
        )

        kb = [
            [
                InlineKeyboardButton("📨 Post", callback_data=f"post_do_{channel_id}"),
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit_do_{channel_id}")
            ],
            [InlineKeyboardButton("❌ Close", callback_data="post_close")]
        ]

        await query.edit_message_text(
            text,
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # POST MODE start
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

        txt = f"🌸 Send or forward the *message to post* in:\n*{md(title)}*"

        await query.edit_message_text(txt, parse_mode="MarkdownV2")
        return

    # EDIT MODE start
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

        txt = f"✏️ Forward the *original message* from *{md(title)}* to edit."

        await query.edit_message_text(txt, parse_mode="MarkdownV2")
        return


# ----------------------------------------------------------
# Handle incoming messages (post/edit content)
# ----------------------------------------------------------
async def user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("USER MESSAGE RECEIVED")

    if not update.message:
        return

    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return

    if user_id not in USER_SESSION:
        return

    session = USER_SESSION[user_id]

    # EDIT: Get original message
    if session["step"] == "await_edit_forward":
        if not update.message.forward_from_chat:
            await update.message.reply_text("❌ Forward the original channel message.")
            return

        if update.message.forward_from_chat.id != session["channel_id"]:
            await update.message.reply_text("❌ This forward is not from the target channel.")
            return

        session["edit_target"] = update.message.forward_from_message_id
        session["step"] = "await_edit_newcontent"

        await update.message.reply_text("✏️ Now send the *new edited content*.", parse_mode="MarkdownV2")
        return

    # EDIT: Receive new content
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
            "Would you like to *add a button*?",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # POST: Receive content
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
            "Would you like to *add a button*?",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )


# ----------------------------------------------------------
# Button flow (yes/no/add more)
# ----------------------------------------------------------
async def post_button_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    print("POST FLOW:", data)

    await query.answer()

    if user_id not in USER_SESSION:
        return

    session = USER_SESSION[user_id]
    msg = session["message"]
    buttons = session["buttons"]

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    # Add a button
    if data == "addbtn_yes":
        session["step"] = "await_button_format"

        txt = (
            "Send button in format:\n\n"
            "`Text - URL`\n"
            "`Text - URL:same`\n"
            "`Text - Label:alert:True`"
        )

        await query.edit_message_text(txt, parse_mode="MarkdownV2")
        return

    # No button → ask to send post
    if data == "addbtn_no":
        session["step"] = "send_post_q"

        kb = [
            [
                InlineKeyboardButton("Yes", callback_data="sendpost_yes"),
                InlineKeyboardButton("No", callback_data="sendpost_no")
            ]
        ]

        await query.edit_message_text(
            "Would you like to *send the post*?",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # Confirm send
    if data == "sendpost_yes":

        # EDIT MODE
        if session["mode"] == "edit":
            try:
                if msg.text:
                    await context.bot.edit_message_text(
                        chat_id=session["channel_id"],
                        message_id=session["edit_target"],
                        text=md(msg.text),
                        parse_mode="MarkdownV2",
                        reply_markup=markup
                    )
                elif msg.photo:
                    await context.bot.edit_message_media(
                        chat_id=session["channel_id"],
                        message_id=session["edit_target"],
                        media=InputMediaPhoto(msg.photo[-1].file_id),
                        reply_markup=markup
                    )

                await query.edit_message_text("✨ Message *edited* successfully!", parse_mode="MarkdownV2")
            except Exception as e:
                await query.edit_message_text(f"❌ Error: `{md(str(e))}`", parse_mode="MarkdownV2")

            USER_SESSION.pop(user_id, None)
            return

        # POST MODE
        if session["mode"] == "post":
            try:
                if msg.photo:
                    await context.bot.send_photo(
                        session["channel_id"],
                        msg.photo[-1].file_id,
                        caption=md(msg.caption or ""),
                        parse_mode="MarkdownV2",
                        reply_markup=markup
                    )
                elif msg.video:
                    await context.bot.send_video(
                        session["channel_id"],
                        msg.video.file_id,
                        caption=md(msg.caption or ""),
                        parse_mode="MarkdownV2",
                        reply_markup=markup
                    )
                else:
                    await context.bot.send_message(
                        session["channel_id"],
                        md(msg.text),
                        parse_mode="MarkdownV2",
                        reply_markup=markup
                    )

                await query.edit_message_text("🌸 Post sent successfully.", parse_mode="MarkdownV2")

            except Exception as e:
                await query.edit_message_text(f"❌ Error: `{md(str(e))}`", parse_mode="MarkdownV2")

            USER_SESSION.pop(user_id, None)
            return

    # Send message WITHOUT buttons
    if data == "sendpost_no":
        kb = [
            [
                InlineKeyboardButton("Yes", callback_data="sendmsg_yes"),
                InlineKeyboardButton("No", callback_data="sendmsg_no")
            ]
        ]

        await query.edit_message_text(
            "Send only the *message content*?",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data == "sendmsg_yes":
        try:
            if msg.photo:
                await context.bot.send_photo(
                    session["channel_id"],
                    msg.photo[-1].file_id,
                    caption=md(msg.caption or ""),
                    parse_mode="MarkdownV2"
                )
            elif msg.video:
                await context.bot.send_video(
                    session["channel_id"],
                    msg.video.file_id,
                    caption=md(msg.caption or ""),
                    parse_mode="MarkdownV2"
                )
            else:
                await context.bot.send_message(
                    session["channel_id"],
                    md(msg.text),
                    parse_mode="MarkdownV2"
                )

            await query.edit_message_text("🌸 Message sent.", parse_mode="MarkdownV2")
        except Exception as e:
            await query.edit_message_text(f"❌ Error: `{md(str(e))}`", parse_mode="MarkdownV2")

        USER_SESSION.pop(user_id, None)
        return

    if data == "sendmsg_no":
        session["step"] = "await_button_format"
        await query.edit_message_text(
            "Send button format:\n"
            "`Text - URL`\n"
            "`Text - URL:same`\n"
            "`Text - Label:alert:True`",
            parse_mode="MarkdownV2"
        )
        return


# ----------------------------------------------------------
# Handle button formatting
# ----------------------------------------------------------
async def button_format_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    if user_id not in USER_SESSION:
        return

    session = USER_SESSION[user_id]
    if session["step"] != "await_button_format":
        return

    raw = update.message.text.strip()
    buttons = session["buttons"]

    # URL Button
    if " - " in raw and "alert:" not in raw:
        try:
            name, url = raw.split(" - ", 1)
            safe_name = md(name)
            safe_url = url.replace(":same", "")

            btn = InlineKeyboardButton(safe_name, url=safe_url)

            if url.endswith(":same") and buttons:
                buttons[-1].append(btn)
            else:
                buttons.append([btn])

        except:
            await update.message.reply_text("❌ Invalid format.")
            return

    # Alert Button
    elif ":alert:" in raw:
        try:
            name, rest = raw.split(" - ", 1)
            msg_alert, val = rest.split(":alert:")
            is_alert = val.lower().strip() == "true"

            cb = f"alert:{md(msg_alert)}:{is_alert}"

            buttons.append([InlineKeyboardButton(md(name), callback_data=cb)])

        except:
            await update.message.reply_text("❌ Bad alert format.")
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

    await update.message.reply_text("🌸 Button added.", reply_markup=InlineKeyboardMarkup(kb))


# ----------------------------------------------------------
# Export Module
# ----------------------------------------------------------
def post_module():
    return [
        (CommandHandler("post", post_handler), 0),

        (CallbackQueryHandler(post_button_handler, pattern="^(post_|page_|edit_)"), 1),

        (CallbackQueryHandler(post_button_flow, pattern="^(addbtn_|sendpost_|sendmsg_)"), 2),

        (MessageHandler(filters.TEXT & ~filters.COMMAND, button_format_handler), 3),

        (MessageHandler(filters.ALL & ~filters.COMMAND, user_message_handler), 4),
        ]
