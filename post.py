import math
import re
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument,
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
# Helper: Safe MarkdownV2 Escape - FIXED VERSION
# ----------------------------------------------------------
def md(text: str) -> str:
    if not text:
        return ""
    # Properly escape all MarkdownV2 reserved characters
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

# ----------------------------------------------------------
# Helper: Clean session
# ----------------------------------------------------------
def clean_session(user_id: int):
    if user_id in USER_SESSION:
        del USER_SESSION[user_id]

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
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(
                "📭 No channels saved yet.\n\n"
                "Use /addch to add a channel first."
            )
        else:
            await update_or_query.edit_message_text(
                "📭 No channels saved yet.\n\n"
                "Use /addch to add a channel first."
            )
        clean_session(user_id)
        return

    total_pages = math.ceil(len(rows) / PAGE_SIZE)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_channels = rows[start:end]

    keyboard = []
    
    # Create buttons in rows of 2 for better mobile UX
    for i in range(0, len(page_channels), 2):
        row = []
        if i < len(page_channels):
            cid, title = page_channels[i]
            # Truncate long titles
            display_title = title[:20] + "..." if len(title) > 20 else title
            row.append(InlineKeyboardButton(
                f"📢 {display_title}", 
                callback_data=f"post_ch_{cid}"
            ))
        if i + 1 < len(page_channels):
            cid, title = page_channels[i + 1]
            display_title = title[:20] + "..." if len(title) > 20 else title
            row.append(InlineKeyboardButton(
                f"📢 {display_title}", 
                callback_data=f"post_ch_{cid}"
            ))
        if row:
            keyboard.append(row)

    # Pagination with better labels
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Previous", callback_data="page_back"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data="page_next"))
    if nav:
        keyboard.append(nav)

    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="page_refresh"),
        InlineKeyboardButton("❌ Cancel", callback_data="post_close")
    ])

    text = (
        f"📢 *Select a Channel*\n\n"
        f"Page {page+1}/{total_pages} • {len(rows)} channels total\n"
        f"Choose a channel to post or edit content:"
    )

    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="MarkdownV2"
        )
    else:
        await update_or_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="MarkdownV2"
        )

# ----------------------------------------------------------
# Handle Buttons
# ----------------------------------------------------------
async def post_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    print(f"POST BUTTON HANDLER: {data}")

    await query.answer()

    if user_id != OWNER_ID:
        await query.edit_message_text("❌ You're not allowed to use this feature.")
        clean_session(user_id)
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

    if data == "page_refresh":
        await send_channel_page(query, context, user_id)
        return

    # Close
    if data == "post_close":
        await query.message.delete()
        clean_session(user_id)
        return

    # Select channel
    if data.startswith("post_ch_"):
        channel_id = int(data.split("_")[2])

        res = db.query(
            "SELECT channel_title FROM channels WHERE channel_id = ?",
            (channel_id,), fetch=True
        )

        if not res:
            await query.edit_message_text("❌ Channel not found in database.")
            clean_session(user_id)
            return

        title = res[0][0]

        text = (
            f"🎯 *Channel Selected*\n\n"
            f"*Name:* {md(title)}\n"
            f"*ID:* `{channel_id}`\n\n"
            f"Choose an action:"
        )

        kb = [
            [
                InlineKeyboardButton("📨 New Post", callback_data=f"post_do_{channel_id}"),
                InlineKeyboardButton("✏️ Edit Post", callback_data=f"edit_do_{channel_id}")
            ],
            [
                InlineKeyboardButton("🔙 Back to List", callback_data="page_refresh"),
                InlineKeyboardButton("❌ Cancel", callback_data="post_close")
            ]
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

        txt = (
            f"📤 *Ready to Post*\n\n"
            f"Channel: *{md(title)}*\n\n"
            f"Please send or forward the message you want to post:\n"
            f"• Text\n• Photo with caption\n• Video with caption\n• Document with caption"
        )

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

        txt = (
            f"✏️ *Edit Mode*\n\n"
            f"Channel: *{md(title)}*\n\n"
            f"Please forward the *original message* from the channel that you want to edit."
        )

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
            await update.message.reply_text(
                "❌ Please forward the original message from the channel.\n\n"
                "Tip: Go to the channel, find the message, and forward it here."
            )
            return

        if update.message.forward_from_chat.id != session["channel_id"]:
            await update.message.reply_text(
                f"❌ This message is not from the target channel.\n\n"
                f"Expected: {session['channel_id']}\n"
                f"Got: {update.message.forward_from_chat.id}"
            )
            return

        session["edit_target"] = update.message.forward_from_message_id
        session["step"] = "await_edit_newcontent"

        await update.message.reply_text(
            "✅ *Original message captured!*\n\n"
            "Now please send the *new content* that will replace it:\n"
            "• Text\n• Photo with caption\n• Video with caption\n• Document with caption",
            parse_mode="MarkdownV2"
        )
        return

    # EDIT: Receive new content
    if session["step"] == "await_edit_newcontent":
        session["message"] = update.message
        session["step"] = "add_button_q"

        kb = [
            [
                InlineKeyboardButton("✅ Yes, Add Button", callback_data="addbtn_yes"),
                InlineKeyboardButton("❌ No Buttons", callback_data="addbtn_no")
            ]
        ]

        await update.message.reply_text(
            "📝 *Content Received!*\n\n"
            "Would you like to *add interactive buttons* to your message?",
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
                InlineKeyboardButton("✅ Yes, Add Button", callback_data="addbtn_yes"),
                InlineKeyboardButton("❌ No Buttons", callback_data="addbtn_no")
            ]
        ]

        await update.message.reply_text(
            "📝 *Content Received!*\n\n"
            "Would you like to *add interactive buttons* to your message?",
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

    print(f"POST FLOW: {data}")

    await query.answer()

    if user_id not in USER_SESSION:
        await query.edit_message_text("❌ Session expired. Please start over with /post")
        return

    session = USER_SESSION[user_id]
    msg = session["message"]
    buttons = session["buttons"]

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    # Add a button
    if data == "addbtn_yes":
        session["step"] = "await_button_format"

        txt = (
            "🔘 *Add Button*\n\n"
            "Send button in one of these formats:\n\n"
            "• *URL Button:*\n"
            "`Button Text - https://example.com`\n\n"
            "• *URL Button (same row):*\n"
            "`Button Text - https://example.com:same`\n\n"
            "• *Alert Button:*\n"
            "`Button Text - Alert Message:alert:true`\n\n"
            "*Examples:*\n"
            "`Visit Website - https://google.com`\n"
            "`Join Channel - https://t.me/channel:same`\n"
            "`Show Alert - Hello this is alert:alert:true`"
        )

        await query.edit_message_text(txt, parse_mode="MarkdownV2")
        return

    # No button → ask to send post
    if data == "addbtn_no":
        session["step"] = "send_post_q"

        kb = [
            [
                InlineKeyboardButton("🚀 Send Now", callback_data="sendpost_yes"),
                InlineKeyboardButton("📝 Add Buttons", callback_data="addbtn_yes")
            ],
            [
                InlineKeyboardButton("🔙 Change Content", callback_data="change_content"),
                InlineKeyboardButton("❌ Cancel", callback_data="post_close")
            ]
        ]

        # Preview message type
        content_type = "text"
        if msg.photo:
            content_type = "photo"
        elif msg.video:
            content_type = "video"
        elif msg.document:
            content_type = "document"

        await query.edit_message_text(
            f"📋 *Ready to {'Edit' if session['mode'] == 'edit' else 'Post'}*\n\n"
            f"*Content Type:* {content_type}\n"
            f"*Channel:* {md(session['channel_title'])}\n"
            f"*Buttons:* {len(buttons)} added\n\n"
            f"Proceed with {'editing' if session['mode'] == 'edit' else 'posting'}?",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # Change content
    if data == "change_content":
        session["step"] = "await_message" if session["mode"] == "post" else "await_edit_newcontent"
        session["buttons"] = []
        
        action = "post" if session["mode"] == "post" else "edit"
        await query.edit_message_text(
            f"🔄 *Change Content*\n\n"
            f"Please send the new content you want to {action}.",
            parse_mode="MarkdownV2"
        )
        return

    # Confirm send
    if data == "sendpost_yes":
        await query.edit_message_text("⏳ Processing...")

        try:
            # EDIT MODE
            if session["mode"] == "edit":
                if msg.text:
                    await context.bot.edit_message_text(
                        chat_id=session["channel_id"],
                        message_id=session["edit_target"],
                        text=msg.text,  # Don't use md() here as we want to preserve original formatting
                        parse_mode=None,  # Disable markdown to avoid parsing errors
                        reply_markup=markup
                    )
                elif msg.photo:
                    await context.bot.edit_message_media(
                        chat_id=session["channel_id"],
                        message_id=session["edit_target"],
                        media=InputMediaPhoto(
                            msg.photo[-1].file_id,
                            caption=msg.caption or "",
                            parse_mode=None
                        ),
                        reply_markup=markup
                    )
                elif msg.video:
                    await context.bot.edit_message_media(
                        chat_id=session["channel_id"],
                        message_id=session["edit_target"],
                        media=InputMediaVideo(
                            msg.video.file_id,
                            caption=msg.caption or "",
                            parse_mode=None
                        ),
                        reply_markup=markup
                    )
                elif msg.document:
                    await context.bot.edit_message_media(
                        chat_id=session["channel_id"],
                        message_id=session["edit_target"],
                        media=InputMediaDocument(
                            msg.document.file_id,
                            caption=msg.caption or "",
                            parse_mode=None
                        ),
                        reply_markup=markup
                    )

                await query.edit_message_text(
                    "✅ *Message edited successfully!*\n\n"
                    f"Channel: {md(session['channel_title'])}",
                    parse_mode="MarkdownV2"
                )

            # POST MODE
            elif session["mode"] == "post":
                if msg.photo:
                    await context.bot.send_photo(
                        session["channel_id"],
                        msg.photo[-1].file_id,
                        caption=msg.caption or "",
                        parse_mode=None,
                        reply_markup=markup
                    )
                elif msg.video:
                    await context.bot.send_video(
                        session["channel_id"],
                        msg.video.file_id,
                        caption=msg.caption or "",
                        parse_mode=None,
                        reply_markup=markup
                    )
                elif msg.document:
                    await context.bot.send_document(
                        session["channel_id"],
                        msg.document.file_id,
                        caption=msg.caption or "",
                        parse_mode=None,
                        reply_markup=markup
                    )
                else:
                    await context.bot.send_message(
                        session["channel_id"],
                        msg.text,
                        parse_mode=None,
                        reply_markup=markup
                    )

                await query.edit_message_text(
                    "✅ *Post sent successfully!*\n\n"
                    f"Channel: {md(session['channel_title'])}",
                    parse_mode="MarkdownV2"
                )

        except Exception as e:
            error_msg = str(e)
            await query.edit_message_text(
                f"❌ *Error occurred*\n\n"
                f"`{md(error_msg)}`\n\n"
                f"Please check:\n"
                f"• Bot admin rights in channel\n"
                f"• Message formatting\n"
                f"• Button URLs validity",
                parse_mode="MarkdownV2"
            )
            print(f"Error in sendpost_yes: {e}")

        clean_session(user_id)
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

    try:
        # URL Button
        if " - " in raw and "alert:" not in raw:
            if ":same" in raw:
                # URL button in same row
                name_url = raw.replace(":same", "")
                name, url = name_url.split(" - ", 1)
                
                if not buttons:
                    buttons.append([InlineKeyboardButton(name.strip(), url=url.strip())])
                else:
                    # Add to last row
                    buttons[-1].append(InlineKeyboardButton(name.strip(), url=url.strip()))
                
                await update.message.reply_text(f"✅ URL button added to existing row: *{name.strip()}*", parse_mode="MarkdownV2")
                
            else:
                # Regular URL button (new row)
                name, url = raw.split(" - ", 1)
                buttons.append([InlineKeyboardButton(name.strip(), url=url.strip())])
                await update.message.reply_text(f"✅ URL button added: *{name.strip()}*", parse_mode="MarkdownV2")

        # Alert Button
        elif ":alert:" in raw:
            name, rest = raw.split(" - ", 1)
            if ":alert:" in rest:
                msg_alert, val = rest.split(":alert:")
                is_alert = val.lower().strip() == "true"
                
                callback_data = f"alert:{msg_alert.strip()}"
                buttons.append([InlineKeyboardButton(name.strip(), callback_data=callback_data)])
                
                await update.message.reply_text(f"✅ Alert button added: *{name.strip()}*", parse_mode="MarkdownV2")
            else:
                await update.message.reply_text("❌ Invalid alert format. Use: `Text - Message:alert:true`", parse_mode="MarkdownV2")
                return

        else:
            await update.message.reply_text(
                "❌ Invalid format. Use:\n"
                "• `Text - URL`\n"
                "• `Text - URL:same`\n"
                "• `Text - Message:alert:true`",
                parse_mode="MarkdownV2"
            )
            return

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error parsing button:\n`{md(str(e))}`\n\n"
            f"Please check the format and try again.",
            parse_mode="MarkdownV2"
        )
        return

    # Ask if user wants to add more buttons
    kb = [
        [
            InlineKeyboardButton("➕ Add More Buttons", callback_data="addbtn_yes"),
            InlineKeyboardButton("✅ Continue", callback_data="addbtn_no")
        ],
        [
            InlineKeyboardButton("🔄 Clear All Buttons", callback_data="clear_buttons"),
            InlineKeyboardButton("❌ Cancel", callback_data="post_close")
        ]
    ]

    button_count = sum(len(row) for row in buttons)
    await update.message.reply_text(
        f"🔘 *Buttons Added*\n\n"
        f"Total buttons: {button_count}\n"
        f"Total rows: {len(buttons)}\n\n"
        f"What would you like to do next?",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ----------------------------------------------------------
# Clear buttons handler
# ----------------------------------------------------------
async def clear_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    if user_id not in USER_SESSION:
        return

    if query.data == "clear_buttons":
        USER_SESSION[user_id]["buttons"] = []
        
        kb = [
            [
                InlineKeyboardButton("➕ Add Buttons", callback_data="addbtn_yes"),
                InlineKeyboardButton("✅ Continue Without", callback_data="addbtn_no")
            ]
        ]

        await query.edit_message_text(
            "🗑️ *All buttons cleared!*\n\n"
            "You can now add new buttons or continue without buttons.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )

# ----------------------------------------------------------
# Export Module
# ----------------------------------------------------------
def post_module():
    return [
        # /post command
        (CommandHandler("post", post_handler), 0),

        # channel selection, page next/back
        (CallbackQueryHandler(post_button_handler, pattern="^(post_ch_|page_|post_do_|edit_do_)"), 1),

        # post flow yes/no/add/send + clear buttons
        (CallbackQueryHandler(post_button_flow, pattern="^(addbtn_|sendpost_|change_content)"), 2),
        
        # clear buttons
        (CallbackQueryHandler(clear_buttons_handler, pattern="^clear_buttons"), 2),

        # button format text
        (MessageHandler(filters.TEXT & ~filters.COMMAND, button_format_handler), 3),

        # normal message handler (post/edit content)
        (MessageHandler(filters.ALL & ~filters.COMMAND, user_message_handler), 4),
    ]
