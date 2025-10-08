import logging
import os
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    InputMediaPhoto, Message, Chat, ChatMember, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode, ChatType, ChatMemberStatus
from telegram.error import BadRequest, TelegramError

# Load environment variables
load_dotenv("bot_token.env")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
OWNER_ID = 5373577888
DATABASE_FILE = "database.json"
MAX_MESSAGE_LENGTH = 4096

@dataclass
class Channel:
    chat_id: int
    title: str
    username: str = ""
    invite_link: str = ""

@dataclass
class PostDraft:
    channel_id: int = None
    content: str = ""
    buttons: List[List[Dict]] = None
    message_id: int = None

@dataclass
class BotSettings:
    start_message: Dict
    help_message: Dict

class UserState(Enum):
    AWAITING_CHANNEL_FORWARD = "awaiting_channel_forward"
    AWAITING_POST_CONTENT = "awaiting_post_content"
    AWAITING_BUTTONS = "awaiting_buttons"
    AWAITING_CHANNEL_SEARCH = "awaiting_channel_search"
    AWAITING_ADMIN_USERNAME = "awaiting_admin_username"
    AWAITING_DEL_ADMIN_USERNAME = "awaiting_del_admin_username"
    AWAITING_START_TEXT = "awaiting_start_text"
    AWAITING_HELP_TEXT = "awaiting_help_text"
    AWAITING_START_BUTTONS = "awaiting_start_buttons"
    AWAITING_HELP_BUTTONS = "awaiting_help_buttons"
    AWAITING_START_IMAGE = "awaiting_start_image"
    AWAITING_HELP_IMAGE = "awaiting_help_image"
    AWAITING_BUTTON_TEXT = "awaiting_button_text"

class Database:
    def __init__(self):
        self.data = {
            "admins": [5373577888, 6170814776, 7569045740],
            "channels": {},
            "button_texts": {},
            "settings": {
                "start_message": {
                    "text": "🤖 **Welcome to Advanced Telegram Bot!**\n\n"
                           "I'm a high-performance bot for managing channels and posting content.\n\n"
                           "**Features:**\n"
                           "• Channel Management\n"
                           "• Scheduled Posting\n"
                           "• Media Support\n"
                           "• Admin Controls\n\n"
                           "Use the buttons below to get started:",
                    "image": None,
                    "buttons": [
                        [["🔹 Help", "help"]],
                        [["🔹 Add Channel", "add_channel"]],
                        [["🔹 Post Panel", "post_panel"]],
                        [["🔹 Settings", "settings"]]
                    ]
                },
                "help_message": {
                    "text": "📖 **Bot Help Guide**\n\n"
                           "**Available Commands:**\n"
                           "• /start - Start the bot\n"
                           "• /help - Show this help message\n"
                           "• /addch - Add a channel (Admin only)\n"
                           "• /post - Open post panel (Admin only)\n"
                           "• /channels - List channels (Admin only)\n"
                           "• /edit_post - Edit existing post (Admin only)\n"
                           "• /add_admin - Add new admin (Owner only)\n"
                           "• /del_admin - Remove admin (Owner only)\n"
                           "• /settings - Configure bot (Owner only)\n\n"
                           "**Admin Features:**\n"
                           "• Add/remove channels\n"
                           "• Create and schedule posts\n"
                           "• Edit existing posts\n"
                           "• Manage bot settings",
                    "image": None,
                    "buttons": [
                        [["⬅️ Back", "start"]],
                        [["⚙️ Settings", "settings"]],
                        [["📢 Channel Manager", "channels"]],
                        [["👮 Admin Controls", "admin_controls"]]
                    ]
                }
            }
        }
        self.load()

    def load(self):
        """Load database from JSON file"""
        try:
            if os.path.exists(DATABASE_FILE):
                with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    self._deep_update(self.data, loaded_data)
                logger.info("Database loaded successfully")
            else:
                self.save()
                logger.info("New database created")
        except Exception as e:
            logger.error(f"Error loading database: {e}")
            self.save()

    def save(self):
        """Save database to JSON file"""
        try:
            with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving database: {e}")

    def _deep_update(self, original, update):
        """Recursively update nested dictionary"""
        for key, value in update.items():
            if isinstance(value, dict) and key in original and isinstance(original[key], dict):
                self._deep_update(original[key], value)
            else:
                original[key] = value

    # Admin methods
    def get_admins(self) -> List[int]:
        return self.data["admins"]

    def add_admin(self, user_id: int) -> bool:
        if user_id not in self.data["admins"]:
            self.data["admins"].append(user_id)
            self.save()
            return True
        return False

    def remove_admin(self, user_id: int) -> bool:
        if user_id in self.data["admins"] and user_id != OWNER_ID:
            self.data["admins"].remove(user_id)
            self.save()
            return True
        return False

    # Channel methods
    def get_channels(self) -> Dict[int, Channel]:
        channels = {}
        for chat_id_str, channel_data in self.data["channels"].items():
            channels[int(chat_id_str)] = Channel(**channel_data)
        return channels

    def add_channel(self, channel: Channel):
        self.data["channels"][str(channel.chat_id)] = asdict(channel)
        self.save()

    def remove_channel(self, chat_id: int):
        if str(chat_id) in self.data["channels"]:
            del self.data["channels"][str(chat_id)]
            self.save()

    # Button texts methods
    def get_button_text(self, button_id: str) -> str:
        return self.data["button_texts"].get(button_id, "No text available.")

    def set_button_text(self, button_id: str, text: str):
        self.data["button_texts"][button_id] = text
        self.save()

    def delete_button_text(self, button_id: str):
        if button_id in self.data["button_texts"]:
            del self.data["button_texts"][button_id]
            self.save()

    # Settings methods
    def get_settings(self) -> BotSettings:
        return BotSettings(**self.data["settings"])

    def update_start_message(self, text: str = None, image: str = None, buttons: List = None):
        if text is not None:
            self.data["settings"]["start_message"]["text"] = text
        if image is not None:
            self.data["settings"]["start_message"]["image"] = image
        if buttons is not None:
            self.data["settings"]["start_message"]["buttons"] = buttons
        self.save()

    def update_help_message(self, text: str = None, image: str = None, buttons: List = None):
        if text is not None:
            self.data["settings"]["help_message"]["text"] = text
        if image is not None:
            self.data["settings"]["help_message"]["image"] = image
        if buttons is not None:
            self.data["settings"]["help_message"]["buttons"] = buttons
        self.save()

# Global instances
db = Database()
user_states: Dict[int, UserState] = {}
post_drafts: Dict[int, PostDraft] = {}
edit_sessions: Dict[int, Dict] = {}
button_editing: Dict[int, Dict] = {}

# Create application with optimized timeouts
application = (Application.builder()
    .token(BOT_TOKEN)
    .read_timeout(10)
    .write_timeout(15)  
    .connect_timeout(10)
    .pool_timeout(10)
    .build())

# Utility functions
def is_admin(user_id: int) -> bool:
    return user_id in db.get_admins()

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

async def safe_send_message(chat_id: int, text: str, **kwargs):
    """Safely send message with error handling"""
    try:
        # Truncate text if too long
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH - 100] + "...\n\n[Message truncated due to length]"
        
        # Try with Markdown first
        if 'parse_mode' not in kwargs:
            kwargs['parse_mode'] = ParseMode.MARKDOWN
        
        return await application.bot.send_message(chat_id, text, **kwargs)
    except BadRequest as e:
        if "can't parse entities" in str(e) or "can't find end" in str(e):
            # Retry without Markdown parsing
            kwargs.pop('parse_mode', None)
            return await application.bot.send_message(chat_id, text, **kwargs)
        raise e

def safe_edit_message(text: str, **kwargs):
    """Safely edit message with error handling"""
    try:
        # Truncate text if too long
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH - 100] + "...\n\n[Message truncated due to length]"
        
        # Try with Markdown first
        if 'parse_mode' not in kwargs:
            kwargs['parse_mode'] = ParseMode.MARKDOWN
        
        return kwargs['query'].edit_message_text(text, **kwargs)
    except BadRequest as e:
        if "can't parse entities" in str(e) or "can't find end" in str(e):
            # Retry without Markdown parsing
            kwargs.pop('parse_mode', None)
            return kwargs['query'].edit_message_text(text, **kwargs)
        raise e

def create_inline_keyboard(buttons_config: List[List[List[str]]]) -> InlineKeyboardMarkup:
    """Create inline keyboard from button configuration"""
    keyboard = []
    for row in buttons_config:
        keyboard_row = []
        for button in row:
            if len(button) == 2:
                text, callback_data = button
                keyboard_row.append(InlineKeyboardButton(text, callback_data=callback_data))
        if keyboard_row:
            keyboard.append(keyboard_row)
    return InlineKeyboardMarkup(keyboard)

def create_url_keyboard(buttons_config: List[List[Dict]]) -> InlineKeyboardMarkup:
    """Create inline keyboard with URL buttons"""
    keyboard = []
    for row in buttons_config:
        keyboard_row = []
        for button in row:
            keyboard_row.append(InlineKeyboardButton(button["text"], url=button["url"]))
        if keyboard_row:
            keyboard.append(keyboard_row)
    return InlineKeyboardMarkup(keyboard)

def parse_button_config(text: str) -> Tuple[List[List[List[str]]], List[str]]:
    """
    Parse button configuration text with multiple formats:
    - URL buttons: ButtonText - url
    - Callback buttons: ButtonText - callback_data
    - Text display buttons: ButtonText - Text when user click
    - Same row: use | separator
    - Special buttons: back, next, close
    """
    buttons = []
    button_texts = {}
    lines = text.strip().split('\n')
    line_number = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        row_buttons = []
        button_pairs = line.split('|')
        
        for pair in button_pairs:
            pair = pair.strip()
            if '-' in pair:
                button_text, action = pair.split('-', 1)
                button_text = button_text.strip()
                action = action.strip()
                
                # Generate unique button ID
                button_id = f"btn_{line_number}_{len(row_buttons)}"
                
                # Determine button type
                if action.lower() in ['back', 'next', 'close']:
                    # Special navigation buttons
                    row_buttons.append([button_text, action.lower()])
                elif action.startswith('http://') or action.startswith('https://'):
                    # URL button
                    row_buttons.append([button_text, f"url_{button_id}"])
                    button_texts[button_id] = action
                elif len(action) > 50 or '\n' in action:
                    # Text display button (long text)
                    row_buttons.append([button_text, f"text_{button_id}"])
                    button_texts[button_id] = action
                else:
                    # Regular callback button
                    row_buttons.append([button_text, action])
        
        if row_buttons:
            buttons.append(row_buttons)
            line_number += 1
    
    return buttons, button_texts

def escape_markdown(text: str) -> str:
    """Escape Markdown special characters"""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

# Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        settings = db.get_settings().start_message
        keyboard = create_inline_keyboard(settings['buttons'])
        
        if settings.get('image'):
            await update.message.reply_photo(
                photo=settings['image'],
                caption=settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await safe_send_message(
                update.effective_chat.id,
                settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    try:
        settings = db.get_settings().help_message
        keyboard = create_inline_keyboard(settings['buttons'])
        
        if settings.get('image'):
            await update.message.reply_photo(
                photo=settings['image'],
                caption=settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await safe_send_message(
                update.effective_chat.id,
                settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"Error in help_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addch command - admin only"""
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        user_states[update.effective_user.id] = UserState.AWAITING_CHANNEL_FORWARD
        await update.message.reply_text(
            "📨 Please forward any message from the channel you want to add.\n\n"
            "**Requirements:**\n"
            "• Bot must be admin in the channel\n"
            "• Bot must have post permissions\n"
            "• Forward any message from the target channel"
        )
    except Exception as e:
        logger.error(f"Error in add_channel_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /post command - admin only"""
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        channels = db.get_channels()
        if not channels:
            await update.message.reply_text("❌ No channels added yet. Use /addch to add channels.")
            return
        
        await show_channel_selection(update, context, "post")
    except Exception as e:
        logger.error(f"Error in post_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /channels command - admin only"""
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        await show_channel_list(update, context)
    except Exception as e:
        logger.error(f"Error in channels_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings command - owner only"""
    try:
        if not is_owner(update.effective_user.id):
            await update.message.reply_text("❌ Owner access required.")
            return
        
        await show_settings_menu_from_command(update)
    except Exception as e:
        logger.error(f"Error in settings_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_admin command - owner only"""
    try:
        if not is_owner(update.effective_user.id):
            await update.message.reply_text("❌ Owner access required.")
            return
        
        user_states[update.effective_user.id] = UserState.AWAITING_ADMIN_USERNAME
        await update.message.reply_text("👮 Send the user ID of the new admin:")
    except Exception as e:
        logger.error(f"Error in add_admin_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def del_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /del_admin command - owner only"""
    try:
        if not is_owner(update.effective_user.id):
            await update.message.reply_text("❌ Owner access required.")
            return
        
        user_states[update.effective_user.id] = UserState.AWAITING_DEL_ADMIN_USERNAME
        await update.message.reply_text("🗑️ Send the user ID of the admin to remove:")
    except Exception as e:
        logger.error(f"Error in del_admin_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

# Settings Menu Handlers
async def show_settings_menu_from_command(update: Update):
    """Show settings menu from command"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Edit Start Text", callback_data="edit_start_text"),
         InlineKeyboardButton("📝 Edit Help Text", callback_data="edit_help_text")],
        [InlineKeyboardButton("🖼️ Start Image", callback_data="edit_start_image"),
         InlineKeyboardButton("🖼️ Help Image", callback_data="edit_help_image")],
        [InlineKeyboardButton("🔘 Start Buttons", callback_data="edit_start_buttons"),
         InlineKeyboardButton("🔘 Help Buttons", callback_data="edit_help_buttons")],
        [InlineKeyboardButton("🗑️ Manage Button Texts", callback_data="manage_button_texts")],
        [InlineKeyboardButton("⬅️ Back", callback_data="start")]
    ])
    
    await update.message.reply_text(
        "⚙️ **Bot Settings Panel**\n\n"
        "Configure your bot's appearance and messages:\n\n"
        "• **Text Messages** - Edit start/help text\n"
        "• **Images** - Add/change images for messages\n"
        "• **Buttons** - Customize inline buttons\n"
        "• **Button Texts** - Manage text display buttons\n\n"
        "Select an option to configure:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# Callback Query Handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    try:
        # Navigation handlers
        if data == "start":
            await show_start_menu(query)
        elif data == "help":
            await show_help_menu(query)
        elif data == "settings":
            if is_owner(user_id):
                await show_settings_menu(query)
            else:
                await query.answer("❌ Owner access required.", show_alert=True)
        elif data == "channels":
            if is_admin(user_id):
                await show_channels_menu(query)
            else:
                await query.answer("❌ Admin access required.", show_alert=True)
        elif data == "admin_controls":
            if is_admin(user_id):
                await show_admin_controls(query)
            else:
                await query.answer("❌ Admin access required.", show_alert=True)
        elif data == "add_channel":
            if is_admin(user_id):
                user_states[user_id] = UserState.AWAITING_CHANNEL_FORWARD
                await query.edit_message_text(
                    "📨 Please forward any message from the channel you want to add."
                )
            else:
                await query.answer("❌ Admin access required.", show_alert=True)
        elif data == "post_panel":
            if is_admin(user_id):
                channels = db.get_channels()
                if not channels:
                    await query.edit_message_text("❌ No channels added yet. Use /addch to add channels.")
                else:
                    await show_channel_selection_query(query, "post")
            else:
                await query.answer("❌ Admin access required.", show_alert=True)
        
        # Settings handlers
        elif data == "edit_start_text":
            if is_owner(user_id):
                await handle_edit_start_text(query)
        elif data == "edit_help_text":
            if is_owner(user_id):
                await handle_edit_help_text(query)
        elif data == "edit_start_image":
            if is_owner(user_id):
                await handle_edit_start_image(query)
        elif data == "edit_help_image":
            if is_owner(user_id):
                await handle_edit_help_image(query)
        elif data == "edit_start_buttons":
            if is_owner(user_id):
                await handle_edit_start_buttons(query)
        elif data == "edit_help_buttons":
            if is_owner(user_id):
                await handle_edit_help_buttons(query)
        elif data == "manage_button_texts":
            if is_owner(user_id):
                await show_button_texts_management(query)
        elif data == "back":
            await show_start_menu(query)
        elif data == "close":
            await query.delete_message()
        
        # Text display buttons
        elif data.startswith("text_"):
            button_id = data[5:]
            text = db.get_button_text(button_id)
            await query.answer(text, show_alert=True)
        
        # Button text management
        elif data.startswith("delete_text_"):
            button_id = data[12:]
            db.delete_button_text(button_id)
            await query.answer("✅ Button text deleted!", show_alert=True)
            await show_button_texts_management(query)
            
    except Exception as e:
        logger.error(f"Error in button_handler: {e}")
        try:
            await query.edit_message_text("❌ An error occurred. Please try again.")
        except:
            await query.answer("❌ Error occurred.", show_alert=True)

# Menu display functions
async def show_start_menu(query):
    """Show start menu"""
    try:
        settings = db.get_settings().start_message
        keyboard = create_inline_keyboard(settings['buttons'])
        
        if settings.get('image'):
            await query.edit_message_media(
                media=InputMediaPhoto(settings['image'], caption=settings['text']),
                reply_markup=keyboard
            )
        else:
            await safe_edit_message(
                settings['text'],
                query=query,
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error in show_start_menu: {e}")
        await query.edit_message_text("❌ Error displaying menu. Please try /start")

async def show_help_menu(query):
    """Show help menu"""
    try:
        settings = db.get_settings().help_message
        keyboard = create_inline_keyboard(settings['buttons'])
        
        if settings.get('image'):
            await query.edit_message_media(
                media=InputMediaPhoto(settings['image'], caption=settings['text']),
                reply_markup=keyboard
            )
        else:
            await safe_edit_message(
                settings['text'],
                query=query,
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error in show_help_menu: {e}")
        await query.edit_message_text("❌ Error displaying help. Please try /help")

async def show_settings_menu(query):
    """Show settings menu"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Edit Start Text", callback_data="edit_start_text"),
         InlineKeyboardButton("📝 Edit Help Text", callback_data="edit_help_text")],
        [InlineKeyboardButton("🖼️ Start Image", callback_data="edit_start_image"),
         InlineKeyboardButton("🖼️ Help Image", callback_data="edit_help_image")],
        [InlineKeyboardButton("🔘 Start Buttons", callback_data="edit_start_buttons"),
         InlineKeyboardButton("🔘 Help Buttons", callback_data="edit_help_buttons")],
        [InlineKeyboardButton("🗑️ Manage Button Texts", callback_data="manage_button_texts")],
        [InlineKeyboardButton("⬅️ Back", callback_data="start")]
    ])
    
    await safe_edit_message(
        "⚙️ **Bot Settings Panel**\n\n"
        "Configure your bot's appearance and messages:\n\n"
        "• **Text Messages** - Edit start/help text\n"
        "• **Images** - Add/change images for messages\n"
        "• **Buttons** - Customize inline buttons\n"
        "• **Button Texts** - Manage text display buttons\n\n"
        "Select an option to configure:",
        query=query,
        reply_markup=keyboard
    )

async def show_button_texts_management(query):
    """Show button texts management menu"""
    button_texts = db.data["button_texts"]
    
    if not button_texts:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="settings")]
        ])
        await safe_edit_message(
            "📝 **Button Texts Management**\n\n"
            "No button texts found. Text display buttons will be created automatically "
            "when you use the format: `ButtonText - Text when user click` in button configuration.",
            query=query,
            reply_markup=keyboard
        )
        return
    
    text_lines = []
    keyboard_buttons = []
    
    for i, (button_id, text_content) in enumerate(button_texts.items()):
        preview = text_content[:50] + "..." if len(text_content) > 50 else text_content
        text_lines.append(f"`{button_id}`: {preview}")
        
        # Add delete button for every 2 items
        if i % 2 == 0:
            row = [InlineKeyboardButton(f"🗑️ {button_id}", callback_data=f"delete_text_{button_id}")]
            if i + 1 < len(button_texts):
                next_id = list(button_texts.keys())[i + 1]
                row.append(InlineKeyboardButton(f"🗑️ {next_id}", callback_data=f"delete_text_{next_id}"))
            keyboard_buttons.append(row)
    
    keyboard_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="settings")])
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await safe_edit_message(
        f"📝 **Button Texts Management**\n\n"
        f"**Total Texts:** {len(button_texts)}\n\n"
        f"**Available Texts:**\n" + "\n".join(text_lines) + "\n\n"
        "Click on 🗑️ to delete a button text.",
        query=query,
        reply_markup=keyboard
    )

async def show_channels_menu(query):
    """Show channels menu"""
    try:
        channels = db.get_channels()
        if not channels:
            await query.edit_message_text("❌ No channels added yet. Use /addch to add channels.")
            return
        
        keyboard_buttons = []
        for channel in list(channels.values())[:10]:
            keyboard_buttons.append([
                InlineKeyboardButton(f"📢 {channel.title}", callback_data=f"channel_{channel.chat_id}")
            ])
        
        keyboard_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="help")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await safe_edit_message(
            f"📢 **Connected Channels**\n\nTotal: {len(channels)} channels",
            query=query,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in show_channels_menu: {e}")
        await query.edit_message_text("❌ Error loading channels. Please try again.")

async def show_admin_controls(query):
    """Show admin controls menu"""
    try:
        admins = db.get_admins()
        admin_list = "\n".join([f"• `{admin_id}`" for admin_id in admins])
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👮 Add Admin", callback_data="add_admin_cmd")],
            [InlineKeyboardButton("🗑️ Remove Admin", callback_data="del_admin_cmd")],
            [InlineKeyboardButton("⬅️ Back", callback_data="help")]
        ])
        
        await safe_edit_message(
            f"👮 **Admin Controls**\n\n**Current Admins:**\n{admin_list}\n\n"
            "Use commands to manage admins:\n"
            "• `/add_admin` - Add new admin\n"
            "• `/del_admin` - Remove admin",
            query=query,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in show_admin_controls: {e}")
        await query.edit_message_text("❌ Error loading admin controls.")

# Settings handlers
async def handle_edit_start_text(query):
    """Handle start text editing"""
    user_states[query.from_user.id] = UserState.AWAITING_START_TEXT
    current_text = db.get_settings().start_message['text']
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await safe_edit_message(
        f"📝 **Edit Start Text**\n\n"
        f"Current text preview:\n`{current_text[:100]}...`\n\n"
        "Send the new start text (supports Markdown):",
        query=query,
        reply_markup=keyboard
    )

async def handle_edit_help_text(query):
    """Handle help text editing"""
    user_states[query.from_user.id] = UserState.AWAITING_HELP_TEXT
    current_text = db.get_settings().help_message['text']
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await safe_edit_message(
        f"📝 **Edit Help Text**\n\n"
        f"Current text preview:\n`{current_text[:100]}...`\n\n"
        "Send the new help text (supports Markdown):",
        query=query,
        reply_markup=keyboard
    )

async def handle_edit_start_image(query):
    """Handle start image editing"""
    user_states[query.from_user.id] = UserState.AWAITING_START_IMAGE
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Remove Image", callback_data="remove_start_image")],
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    current_image = db.get_settings().start_message.get('image')
    image_status = "✅ Currently has image" if current_image else "❌ No image set"
    
    await query.edit_message_text(
        f"🖼️ **Change Start Image**\n\n"
        f"{image_status}\n\n"
        "Send a new image or photo, or click 'Remove Image' to clear:",
        reply_markup=keyboard
    )

async def handle_edit_help_image(query):
    """Handle help image editing"""
    user_states[query.from_user.id] = UserState.AWAITING_HELP_IMAGE
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Remove Image", callback_data="remove_help_image")],
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    current_image = db.get_settings().help_message.get('image')
    image_status = "✅ Currently has image" if current_image else "❌ No image set"
    
    await query.edit_message_text(
        f"🖼️ **Change Help Image**\n\n"
        f"{image_status}\n\n"
        "Send a new image or photo, or click 'Remove Image' to clear:",
        reply_markup=keyboard
    )

async def handle_edit_start_buttons(query):
    """Handle start buttons editing"""
    user_states[query.from_user.id] = UserState.AWAITING_START_BUTTONS
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await safe_edit_message(
        "🔘 **Edit Start Buttons**\n\n"
        "**Button Format Guide:**\n"
        "```\n"
        "Button1 - callback_data | Button2 - http://example.com\n"
        "Back - back | Next - next | Close - close\n"
        "Info - This is the text that will be displayed\n"
        "```\n\n"
        "**Formats:**\n"
        "• `Text - callback_data` - Regular button\n"
        "• `Text - url` - URL button\n"
        "• `Text - Text to display` - Text display button\n"
        "• `back - back` - Back button\n"
        "• `next - next` - Next button\n"
        "• `close - close` - Close button\n"
        "• Use `|` for same row\n"
        "• New line for new row\n\n"
        "Send new button configuration:",
        query=query,
        reply_markup=keyboard
    )

async def handle_edit_help_buttons(query):
    """Handle help buttons editing"""
    user_states[query.from_user.id] = UserState.AWAITING_HELP_BUTTONS
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await safe_edit_message(
        "🔘 **Edit Help Buttons**\n\n"
        "**Button Format Guide:**\n"
        "```\n"
        "Button1 - callback_data | Button2 - http://example.com\n"
        "Back - back | Next - next | Close - close\n"
        "Info - This is the text that will be displayed\n"
        "```\n\n"
        "**Formats:**\n"
        "• `Text - callback_data` - Regular button\n"
        "• `Text - url` - URL button\n"
        "• `Text - Text to display` - Text display button\n"
        "• `back - back` - Back button\n"
        "• `next - next` - Next button\n"
        "• `close - close` - Close button\n"
        "• Use `|` for same row\n"
        "• New line for new row\n\n"
        "Send new button configuration:",
        query=query,
        reply_markup=keyboard
    )

# Message Handler for text inputs
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for various states"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    
    try:
        if state == UserState.AWAITING_ADMIN_USERNAME:
            await handle_add_admin(update, text)
        elif state == UserState.AWAITING_DEL_ADMIN_USERNAME:
            await handle_del_admin(update, text)
        elif state == UserState.AWAITING_START_TEXT:
            await handle_save_start_text(update, text)
        elif state == UserState.AWAITING_HELP_TEXT:
            await handle_save_help_text(update, text)
        elif state == UserState.AWAITING_START_BUTTONS:
            await handle_save_start_buttons(update, text)
        elif state == UserState.AWAITING_HELP_BUTTONS:
            await handle_save_help_buttons(update, text)
            
    except Exception as e:
        logger.error(f"Error in message_handler: {e}")
        await update.message.reply_text("❌ An error occurred while processing your input.")

# Photo Handler for image inputs
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages for image states"""
    user_id = update.effective_user.id
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    photo = update.message.photo[-1]  # Get highest resolution photo
    
    try:
        if state == UserState.AWAITING_START_IMAGE:
            await handle_save_start_image(update, photo.file_id)
        elif state == UserState.AWAITING_HELP_IMAGE:
            await handle_save_help_image(update, photo.file_id)
            
    except Exception as e:
        logger.error(f"Error in photo_handler: {e}")
        await update.message.reply_text("❌ An error occurred while processing the image.")

# Settings save handlers
async def handle_save_start_text(update: Update, text: str):
    """Save new start text"""
    db.update_start_message(text=text)
    del user_states[update.effective_user.id]
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
        [InlineKeyboardButton("📱 View Start", callback_data="start")]
    ])
    
    await update.message.reply_text(
        "✅ **Start text updated successfully!**\n\n"
        "Your new start message has been saved.",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_save_help_text(update: Update, text: str):
    """Save new help text"""
    db.update_help_message(text=text)
    del user_states[update.effective_user.id]
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
        [InlineKeyboardButton("📱 View Help", callback_data="help")]
    ])
    
    await update.message.reply_text(
        "✅ **Help text updated successfully!**\n\n"
        "Your new help message has been saved.",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_save_start_image(update: Update, file_id: str):
    """Save new start image"""
    db.update_start_message(image=file_id)
    del user_states[update.effective_user.id]
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
        [InlineKeyboardButton("📱 View Start", callback_data="start")]
    ])
    
    await update.message.reply_text(
        "✅ **Start image updated successfully!**\n\n"
        "Your new start image has been saved.",
        reply_markup=keyboard
    )

async def handle_save_help_image(update: Update, file_id: str):
    """Save new help image"""
    db.update_help_message(image=file_id)
    del user_states[update.effective_user.id]
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
        [InlineKeyboardButton("📱 View Help", callback_data="help")]
    ])
    
    await update.message.reply_text(
        "✅ **Help image updated successfully!**\n\n"
        "Your new help image has been saved.",
        reply_markup=keyboard
    )

async def handle_save_start_buttons(update: Update, text: str):
    """Save new start buttons"""
    try:
        buttons, button_texts = parse_button_config(text)
        
        if buttons:
            # Save button texts to database
            for button_id, text_content in button_texts.items():
                db.set_button_text(button_id, text_content)
            
            db.update_start_message(buttons=buttons)
            del user_states[update.effective_user.id]
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
                [InlineKeyboardButton("📱 View Start", callback_data="start")]
            ])
            
            await update.message.reply_text(
                f"✅ **Start buttons updated successfully!**\n\n"
                f"Added {len(buttons)} button rows.\n"
                f"Saved {len(button_texts)} text display buttons.",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                "❌ Invalid button format. Please check the format guide and try again."
            )
    except Exception as e:
        logger.error(f"Error saving start buttons: {e}")
        await update.message.reply_text("❌ Error saving buttons. Please check the format.")

async def handle_save_help_buttons(update: Update, text: str):
    """Save new help buttons"""
    try:
        buttons, button_texts = parse_button_config(text)
        
        if buttons:
            # Save button texts to database
            for button_id, text_content in button_texts.items():
                db.set_button_text(button_id, text_content)
            
            db.update_help_message(buttons=buttons)
            del user_states[update.effective_user.id]
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
                [InlineKeyboardButton("📱 View Help", callback_data="help")]
            ])
            
            await update.message.reply_text(
                f"✅ **Help buttons updated successfully!**\n\n"
                f"Added {len(buttons)} button rows.\n"
                f"Saved {len(button_texts)} text display buttons.",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                "❌ Invalid button format. Please check the format guide and try again."
            )
    except Exception as e:
        logger.error(f"Error saving help buttons: {e}")
        await update.message.reply_text("❌ Error saving buttons. Please check the format.")

# Admin management handlers
async def handle_add_admin(update: Update, text: str):
    """Handle adding new admin"""
    user_id = update.effective_user.id
    
    try:
        new_admin_id = int(text)
        if db.add_admin(new_admin_id):
            await update.message.reply_text(f"✅ Successfully added new admin: `{new_admin_id}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ Admin already exists.")
    
    except ValueError:
        await update.message.reply_text("❌ Please send a valid user ID (numbers only).")
    
    if user_id in user_states:
        del user_states[user_id]

async def handle_del_admin(update: Update, text: str):
    """Handle removing admin"""
    user_id = update.effective_user.id
    
    try:
        admin_id = int(text)
        if db.remove_admin(admin_id):
            await update.message.reply_text(f"✅ Admin removed successfully: `{admin_id}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ Admin not found or cannot remove owner.")
    
    except ValueError:
        await update.message.reply_text("❌ Please send a valid user ID (numbers only).")
    
    if user_id in user_states:
        del user_states[user_id]

# Forward Handler with proper error handling
async def forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle forwarded messages for channel addition"""
    user_id = update.effective_user.id
    
    if user_id not in user_states or user_states[user_id] != UserState.AWAITING_CHANNEL_FORWARD:
        return
    
    try:
        message = update.message
        
        # Check if message is forwarded from a channel
        if not message.forward_from_chat or message.forward_from_chat.type != ChatType.CHANNEL:
            await update.message.reply_text("❌ Please forward a message from a channel.")
            return
        
        chat = message.forward_from_chat
        
        # Check if bot is admin in the channel with proper permissions
        try:
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            
            if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                await update.message.reply_text(
                    "⚠️ **Bot must be an admin in this channel before adding.**\n\n"
                    "Please make sure:\n"
                    "• Bot is added as administrator\n"
                    "• Bot has post message permissions\n"
                    "• Bot can manage posts (if available)"
                )
                return
            
            # Check if bot can post messages
            if not getattr(bot_member, 'can_post_messages', False):
                await update.message.reply_text(
                    "⚠️ **Bot doesn't have permission to post messages in this channel.**\n\n"
                    "Please grant the bot 'Post Messages' permission in channel settings."
                )
                return
            
            # Add channel to database
            channel = Channel(
                chat_id=chat.id,
                title=chat.title,
                username=getattr(chat, 'username', ''),
                invite_link=getattr(chat, 'invite_link', '')
            )
            db.add_channel(channel)
            
            del user_states[user_id]
            await update.message.reply_text(
                f"✅ **Channel added successfully!**\n\n"
                f"**Title:** {chat.title}\n"
                f"**ID:** `{chat.id}`\n"
                f"**Username:** @{chat.username if chat.username else 'N/A'}\n\n"
                "You can now use /post to create posts in this channel.",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except BadRequest as e:
            if "chat not found" in str(e).lower() or "bot is not a member" in str(e).lower():
                await update.message.reply_text(
                    "❌ **Bot is not a member of this channel.**\n\n"
                    "Please add the bot to the channel first and make it an administrator."
                )
            else:
                raise e
                
    except TelegramError as e:
        logger.error(f"Telegram error in forward_handler: {e}")
        await update.message.reply_text("❌ Error verifying channel. Please try again.")
    except Exception as e:
        logger.error(f"Unexpected error in forward_handler: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again.")

# Channel management functions
async def show_channel_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    """Show channel selection for posting"""
    try:
        channels = db.get_channels()
        keyboard_buttons = []
        
        for channel in list(channels.values())[:8]:
            keyboard_buttons.append([
                InlineKeyboardButton(f"📢 {channel.title}", callback_data=f"select_channel_{channel.chat_id}")
            ])
        
        keyboard_buttons.append([InlineKeyboardButton("🔍 Search Channel", callback_data="search_channel")])
        keyboard_buttons.append([InlineKeyboardButton("❌ Close", callback_data="close")])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await update.message.reply_text(
            "📢 **Select a channel to post in:**\n\n"
            "Choose from your connected channels:",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in show_channel_selection: {e}")
        await update.message.reply_text("❌ Error loading channels. Please try again.")

async def show_channel_selection_query(query, action: str):
    """Show channel selection for query"""
    try:
        channels = db.get_channels()
        keyboard_buttons = []
        
        for channel in list(channels.values())[:8]:
            keyboard_buttons.append([
                InlineKeyboardButton(f"📢 {channel.title}", callback_data=f"select_channel_{channel.chat_id}")
            ])
        
        keyboard_buttons.append([InlineKeyboardButton("🔍 Search Channel", callback_data="search_channel")])
        keyboard_buttons.append([InlineKeyboardButton("❌ Close", callback_data="close")])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await query.edit_message_text(
            "📢 **Select a channel to post in:**\n\n"
            "Choose from your connected channels:",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in show_channel_selection_query: {e}")
        await query.edit_message_text("❌ Error loading channels. Please try again.")

async def show_channel_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display channel list"""
    try:
        channels = db.get_channels()
        if not channels:
            await update.message.reply_text("❌ No channels added yet. Use /addch to add channels.")
            return
        
        channel_list = "\n".join([f"• **{channel.title}** (ID: `{channel.chat_id}`)" for channel in channels.values()])
        
        await update.message.reply_text(
            f"📢 **Connected Channels**\n\n{channel_list}\n\n**Total:** {len(channels)} channels",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in show_channel_list: {e}")
        await update.message.reply_text("❌ Error loading channel list. Please try again.")

# Setup handlers
def setup_handlers():
    """Setup all command and callback handlers"""
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addch", add_channel_command))
    application.add_handler(CommandHandler("post", post_command))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("del_admin", del_admin_command))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(MessageHandler(filters.FORWARDED, forward_handler))

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ An error occurred while processing your request. Please try again."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")

# Main function
def main():
    """Main function to run the bot"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables!")
        return
    
    logger.info("Starting Advanced Telegram Bot with enhanced button system...")
    
    # Setup all handlers
    setup_handlers()
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Run the bot with polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
