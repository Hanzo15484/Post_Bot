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
    InputMediaPhoto, Message, Chat, ChatMember
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

class Database:
    def __init__(self):
        self.data = {
            "admins": [5373577888, 6170814776, 7569045740],
            "channels": {},
            "button_texts": {},
            "custom_pages": {
                "about": "🤖 **About This Bot**\n\nThis is an advanced Telegram bot for channel management and content posting. Built with Python and python-telegram-bot library.",
                "features": "🚀 **Features**\n\n• **Channel Management** - Add and manage multiple channels\n• **Post Scheduling** - Schedule posts for later\n• **Media Support** - Support for images and documents\n• **Admin Controls** - Multi-level admin system\n• **Button System** - Advanced inline button system",
                "contact": "📞 **Contact Us**\n\nFor support and inquiries, please contact the bot owner."
            },
            "settings": {
                "start_message": {
                    "text": "🤖 **Welcome to Advanced Telegram Bot!**\n\n"
                           "I'm a high-performance bot for managing channels and posting content.\n\n"
                           "Use the buttons below to navigate:",
                    "image": None,
                    "buttons": [
                        [["📖 Help", "help"], ["⚙️ Settings", "settings"]],
                        [["📢 Add Channel", "add_channel"], ["📝 Post Panel", "post_panel"]],
                        [["📋 Channel List", "channels"], ["👮 Admin Panel", "admin_controls"]],
                        [["ℹ️ About", "about"], ["🚀 Features", "features"]],
                        [["📞 Contact", "contact"], ["➡️ Next", "next_page_1"]]
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
                           "• /settings - Configure bot (Owner only)\n"
                           "• /add_admin - Add new admin (Owner only)\n"
                           "• /del_admin - Remove admin (Owner only)\n\n"
                           "**Button System:**\n"
                           "• **Text - url** - Opens URL\n"
                           "• **Text - callback** - Executes action\n"
                           "• **Text - display text** - Shows text alert\n"
                           "• **back - back** - Goes back\n"
                           "• **next - next** - Next page\n"
                           "• **close - close** - Closes menu",
                    "image": None,
                    "buttons": [
                        [["⬅️ Back", "start"], ["❌ Close", "close"]]
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

    # Custom pages methods
    def get_custom_page(self, page_id: str) -> str:
        return self.data["custom_pages"].get(page_id, "Page not found.")

    def set_custom_page(self, page_id: str, content: str):
        self.data["custom_pages"][page_id] = content
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
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH - 100] + "...\n\n[Message truncated]"
        
        if 'parse_mode' not in kwargs:
            kwargs['parse_mode'] = ParseMode.MARKDOWN
        
        return await application.bot.send_message(chat_id, text, **kwargs)
    except BadRequest as e:
        if "can't parse entities" in str(e):
            kwargs.pop('parse_mode', None)
            return await application.bot.send_message(chat_id, text, **kwargs)
        raise e

async def safe_edit_message_text(query, text: str, **kwargs):
    """Safely edit message with error handling"""
    try:
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH - 100] + "...\n\n[Message truncated]"
        
        if 'parse_mode' not in kwargs:
            kwargs['parse_mode'] = ParseMode.MARKDOWN
        
        return await query.edit_message_text(text, **kwargs)
    except BadRequest as e:
        if "can't parse entities" in str(e):
            kwargs.pop('parse_mode', None)
            return await query.edit_message_text(text, **kwargs)
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

def parse_button_config(text: str) -> Tuple[List[List[List[str]]], Dict[str, str]]:
    """
    Parse button configuration with formats:
    - Text - url (URL button)
    - Text - display text (Alert button)
    - Text - callback_data (Action button)
    - back - back (Back navigation)
    - next - next (Next page)
    - close - close (Close menu)
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
                
                button_id = f"btn_{line_number}_{len(row_buttons)}"
                
                # Determine button type
                if action.lower() in ['back', 'next', 'close']:
                    # Navigation buttons
                    row_buttons.append([button_text, action.lower()])
                elif action.startswith(('http://', 'https://')):
                    # URL button
                    row_buttons.append([button_text, f"url_{button_id}"])
                    button_texts[button_id] = action
                elif action.startswith('next_page_'):
                    # Next page button
                    row_buttons.append([button_text, action])
                elif len(action) > 30 or any(keyword in action.lower() for keyword in ['display', 'show', 'alert']):
                    # Text display button
                    row_buttons.append([button_text, f"text_{button_id}"])
                    button_texts[button_id] = action
                elif action in ['help', 'about', 'features', 'contact', 'settings', 'channels', 'admin_controls', 'add_channel', 'post_panel']:
                    # Standard callback buttons
                    row_buttons.append([button_text, action])
                else:
                    # Custom callback button
                    row_buttons.append([button_text, action])
        
        if row_buttons:
            buttons.append(row_buttons)
            line_number += 1
    
    return buttons, button_texts

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
            "• Bot must have post permissions"
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
        
        await show_channel_list(update, context)
    except Exception as e:
        logger.error(f"Error in post_command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /channels command - admin only"""
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
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
                await query.edit_message_text("📨 Please forward any message from the channel you want to add.")
            else:
                await query.answer("❌ Admin access required.", show_alert=True)
        elif data == "post_panel":
            if is_admin(user_id):
                channels = db.get_channels()
                if not channels:
                    await query.edit_message_text("❌ No channels added yet. Use /addch to add channels.")
                else:
                    await show_channel_selection(query)
            else:
                await query.answer("❌ Admin access required.", show_alert=True)
        
        # Custom pages
        elif data in ["about", "features", "contact"]:
            await show_custom_page(query, data)
        
        # Next pages
        elif data.startswith("next_page_"):
            page_num = data.split("_")[2]
            await show_next_page(query, int(page_num))
        
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
        
        # Navigation buttons
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
            await safe_edit_message_text(
                query,
                settings['text'],
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
            await safe_edit_message_text(
                query,
                settings['text'],
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error in show_help_menu: {e}")
        await query.edit_message_text("❌ Error displaying help. Please try /help")

async def show_custom_page(query, page_id: str):
    """Show custom page with back and close buttons"""
    try:
        content = db.get_custom_page(page_id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="start"),
             InlineKeyboardButton("❌ Close", callback_data="close")]
        ])
        
        await safe_edit_message_text(
            query,
            content,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error showing custom page {page_id}: {e}")
        await query.edit_message_text("❌ Error loading page.")

async def show_next_page(query, page_num: int):
    """Show next page in navigation"""
    try:
        pages = {
            1: "📄 **Additional Features**\n\n"
                "**Advanced Post Management:**\n"
                "• Schedule posts for specific times\n"
                "• Edit existing posts\n"
                "• Multi-channel posting\n"
                "• Media and file support\n\n"
                "**Admin Features:**\n"
                "• Multi-admin support\n"
                "• Permission management\n"
                "• Activity logging",
            2: "📄 **More Information**\n\n"
                "**Technical Details:**\n"
                "• Built with Python\n"
                "• Uses python-telegram-bot\n"
                "• JSON database system\n"
                "• Async/await architecture\n\n"
                "**Support:**\n"
                "Contact the bot owner for support."
        }
        
        content = pages.get(page_num, "📄 **Page Not Found**\n\nThis page doesn't exist.")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="start"),
             InlineKeyboardButton("❌ Close", callback_data="close")]
        ])
        
        await safe_edit_message_text(
            query,
            content,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error showing next page {page_num}: {e}")
        await query.edit_message_text("❌ Error loading page.")

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
        "Configure your bot's appearance and messages:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

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
    
    await safe_edit_message_text(
        query,
        "⚙️ **Bot Settings Panel**\n\n"
        "Configure your bot's appearance and messages:",
        reply_markup=keyboard
    )

async def show_button_texts_management(query):
    """Show button texts management menu"""
    button_texts = db.data["button_texts"]
    
    if not button_texts:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="settings")]
        ])
        await safe_edit_message_text(
            query,
            "📝 **Button Texts Management**\n\n"
            "No button texts found. Create text display buttons using the format:\n"
            "`ButtonText - Text to display when clicked`",
            reply_markup=keyboard
        )
        return
    
    text_lines = []
    keyboard_buttons = []
    
    for i, (button_id, text_content) in enumerate(button_texts.items()):
        preview = text_content[:50] + "..." if len(text_content) > 50 else text_content
        text_lines.append(f"`{button_id}`: {preview}")
        
        if i % 2 == 0:
            row = [InlineKeyboardButton(f"🗑️ {button_id}", callback_data=f"delete_text_{button_id}")]
            if i + 1 < len(button_texts):
                next_id = list(button_texts.keys())[i + 1]
                row.append(InlineKeyboardButton(f"🗑️ {next_id}", callback_data=f"delete_text_{next_id}"))
            keyboard_buttons.append(row)
    
    keyboard_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="settings")])
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await safe_edit_message_text(
        query,
        f"📝 **Button Texts Management**\n\n"
        f"**Total Texts:** {len(button_texts)}\n\n"
        f"**Available Texts:**\n" + "\n".join(text_lines) + "\n\n"
        "Click 🗑️ to delete a button text.",
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
        for channel in list(channels.values())[:8]:
            keyboard_buttons.append([
                InlineKeyboardButton(f"📢 {channel.title}", callback_data=f"channel_{channel.chat_id}")
            ])
        
        keyboard_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="start")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await safe_edit_message_text(
            query,
            f"📢 **Connected Channels**\n\nSelect a channel:",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in show_channels_menu: {e}")
        await query.edit_message_text("❌ Error loading channels.")

async def show_channel_selection(query):
    """Show channel selection for posting"""
    try:
        channels = db.get_channels()
        keyboard_buttons = []
        
        for channel in list(channels.values())[:8]:
            keyboard_buttons.append([
                InlineKeyboardButton(f"📢 {channel.title}", callback_data=f"select_{channel.chat_id}")
            ])
        
        keyboard_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="start")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await safe_edit_message_text(
            query,
            "📝 **Post Panel**\n\nSelect a channel to post in:",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in show_channel_selection: {e}")
        await query.edit_message_text("❌ Error loading channels.")

async def show_admin_controls(query):
    """Show admin controls menu"""
    try:
        admins = db.get_admins()
        admin_list = "\n".join([f"• `{admin_id}`" for admin_id in admins])
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👮 Add Admin", callback_data="add_admin_cmd")],
            [InlineKeyboardButton("🗑️ Remove Admin", callback_data="del_admin_cmd")],
            [InlineKeyboardButton("⬅️ Back", callback_data="start")]
        ])
        
        await safe_edit_message_text(
            query,
            f"👮 **Admin Controls**\n\n**Current Admins:**\n{admin_list}",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in show_admin_controls: {e}")
        await query.edit_message_text("❌ Error loading admin controls.")

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
        await update.message.reply_text("❌ Error loading channel list.")

# Settings handlers
async def handle_edit_start_text(query):
    """Handle start text editing"""
    user_states[query.from_user.id] = UserState.AWAITING_START_TEXT
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await safe_edit_message_text(
        query,
        "📝 **Edit Start Text**\n\nSend the new start text:",
        reply_markup=keyboard
    )

async def handle_edit_help_text(query):
    """Handle help text editing"""
    user_states[query.from_user.id] = UserState.AWAITING_HELP_TEXT
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await safe_edit_message_text(
        query,
        "📝 **Edit Help Text**\n\nSend the new help text:",
        reply_markup=keyboard
    )

async def handle_edit_start_image(query):
    """Handle start image editing"""
    user_states[query.from_user.id] = UserState.AWAITING_START_IMAGE
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Remove Image", callback_data="remove_start_image")],
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await query.edit_message_text(
        "🖼️ **Change Start Image**\n\nSend a new image or click 'Remove Image':",
        reply_markup=keyboard
    )

async def handle_edit_help_image(query):
    """Handle help image editing"""
    user_states[query.from_user.id] = UserState.AWAITING_HELP_IMAGE
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Remove Image", callback_data="remove_help_image")],
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await query.edit_message_text(
        "🖼️ **Change Help Image**\n\nSend a new image or click 'Remove Image':",
        reply_markup=keyboard
    )

async def handle_edit_start_buttons(query):
    """Handle start buttons editing"""
    user_states[query.from_user.id] = UserState.AWAITING_START_BUTTONS
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await safe_edit_message_text(
        query,
        "🔘 **Edit Start Buttons**\n\n"
        "**Button Format Guide:**\n"
        "```\n"
        "Button1 - callback_data | Button2 - http://example.com\n"
        "Back - back | Next - next | Close - close\n"
        "Info - This text will be displayed\n"
        "```\n\n"
        "Send new button configuration:",
        reply_markup=keyboard
    )

async def handle_edit_help_buttons(query):
    """Handle help buttons editing"""
    user_states[query.from_user.id] = UserState.AWAITING_HELP_BUTTONS
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="settings")]
    ])
    
    await safe_edit_message_text(
        query,
        "🔘 **Edit Help Buttons**\n\n"
        "**Button Format Guide:**\n"
        "```\n"
        "Button1 - callback_data | Button2 - http://example.com\n"
        "Back - back | Next - next | Close - close\n"
        "Info - This text will be displayed\n"
        "```\n\n"
        "Send new button configuration:",
        reply_markup=keyboard
    )

# Message Handler
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
        await update.message.reply_text("❌ An error occurred.")

# Photo Handler
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages"""
    user_id = update.effective_user.id
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    photo = update.message.photo[-1]
    
    try:
        if state == UserState.AWAITING_START_IMAGE:
            await handle_save_start_image(update, photo.file_id)
        elif state == UserState.AWAITING_HELP_IMAGE:
            await handle_save_help_image(update, photo.file_id)
            
    except Exception as e:
        logger.error(f"Error in photo_handler: {e}")
        await update.message.reply_text("❌ Error processing image.")

# Forward Handler
async def forwarded_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle forwarded messages for channel addition"""
    message = update.message

    if not message:
        return  

    # Restrict only to private chat
    if message.chat.type != "private":
        return  

    if not getattr(message, "forward_origin", None):
        await message.reply_text("⚠️ This message is not forwarded from a channel!")
        return

    origin = message.forward_origin

    if origin.type == "channel":
        channel_id = str(origin.chat.id)
        channel_title = origin.chat.title
        
        # Check if bot is admin in the channel
        try:
            bot_member = await context.bot.get_chat_member(origin.chat.id, context.bot.id)
            
            if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                await message.reply_text("⚠️ Bot must be an admin in this channel before adding.")
                return
            
            if not getattr(bot_member, 'can_post_messages', False):
                await message.reply_text("⚠️ Bot doesn't have permission to post messages.")
                return
            
            # Add channel to database
            channel = Channel(
                chat_id=origin.chat.id,
                title=channel_title,
                username=getattr(origin.chat, 'username', ''),
                invite_link=getattr(origin.chat, 'invite_link', '')
            )
            db.add_channel(channel)
            
            await message.reply_text(
                f"✅ **Channel added successfully!**\n\n"
                f"**Title:** {channel_title}\n"
                f"**ID:** `{channel_id}`\n\n"
                "You can now use /post to create posts.",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except BadRequest as e:
            if "chat not found" in str(e).lower():
                await message.reply_text("❌ Bot is not a member of this channel.")
            else:
                raise e
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            await message.reply_text("❌ Error adding channel.")

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
        "✅ **Start text updated successfully!**",
        reply_markup=keyboard
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
        "✅ **Help text updated successfully!**",
        reply_markup=keyboard
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
        "✅ **Start image updated successfully!**",
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
        "✅ **Help image updated successfully!**",
        reply_markup=keyboard
    )

async def handle_save_start_buttons(update: Update, text: str):
    """Save new start buttons"""
    try:
        buttons, button_texts = parse_button_config(text)
        
        if buttons:
            for button_id, text_content in button_texts.items():
                db.set_button_text(button_id, text_content)
            
            db.update_start_message(buttons=buttons)
            del user_states[update.effective_user.id]
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
                [InlineKeyboardButton("📱 View Start", callback_data="start")]
            ])
            
            await update.message.reply_text(
                f"✅ **Start buttons updated!**\n\n"
                f"Added {len(buttons)} button rows.\n"
                f"Saved {len(button_texts)} text buttons.",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text("❌ Invalid button format.")
    except Exception as e:
        logger.error(f"Error saving start buttons: {e}")
        await update.message.reply_text("❌ Error saving buttons.")

async def handle_save_help_buttons(update: Update, text: str):
    """Save new help buttons"""
    try:
        buttons, button_texts = parse_button_config(text)
        
        if buttons:
            for button_id, text_content in button_texts.items():
                db.set_button_text(button_id, text_content)
            
            db.update_help_message(buttons=buttons)
            del user_states[update.effective_user.id]
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
                [InlineKeyboardButton("📱 View Help", callback_data="help")]
            ])
            
            await update.message.reply_text(
                f"✅ **Help buttons updated!**\n\n"
                f"Added {len(buttons)} button rows.\n"
                f"Saved {len(button_texts)} text buttons.",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text("❌ Invalid button format.")
    except Exception as e:
        logger.error(f"Error saving help buttons: {e}")
        await update.message.reply_text("❌ Error saving buttons.")

# Admin management
async def handle_add_admin(update: Update, text: str):
    """Handle adding new admin"""
    user_id = update.effective_user.id
    
    try:
        new_admin_id = int(text)
        if db.add_admin(new_admin_id):
            await update.message.reply_text(f"✅ Added admin: `{new_admin_id}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ Admin already exists.")
    except ValueError:
        await update.message.reply_text("❌ Please send a valid user ID.")
    
    if user_id in user_states:
        del user_states[user_id]

async def handle_del_admin(update: Update, text: str):
    """Handle removing admin"""
    user_id = update.effective_user.id
    
    try:
        admin_id = int(text)
        if db.remove_admin(admin_id):
            await update.message.reply_text(f"✅ Removed admin: `{admin_id}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ Admin not found or cannot remove owner.")
    except ValueError:
        await update.message.reply_text("❌ Please send a valid user ID.")
    
    if user_id in user_states:
        del user_states[user_id]

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
    application.add_handler(MessageHandler(filters.FORWARDED, forwarded_handler))

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Exception: {context.error}", exc_info=context.error)

# Main function
def main():
    """Main function to run the bot"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found!")
        return
    
    logger.info("Starting Advanced Telegram Bot...")
    
    # Setup all handlers
    setup_handlers()
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Run the bot
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
