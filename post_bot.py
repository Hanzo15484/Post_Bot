import logging
import os
import json
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

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

@dataclass
class Channel:
    chat_id: int
    title: str
    username: str = ""

@dataclass
class PostDraft:
    channel_id: int = None
    content: str = ""
    buttons: List[List[Dict]] = None

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

class Database:
    def __init__(self):
        self.data = {
            "admins": [5373577888, 6170814776, 7569045740],
            "channels": {},
            "settings": {
                "start_message": {
                    "text": "🤖 Welcome to the Advanced Telegram Bot!\n\nUse the buttons below to navigate:",
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
                           "• /start - Start the bot\n"
                           "• /help - Show this help message\n"
                           "• /addch - Add a channel (Admin only)\n"
                           "• /post - Open post panel (Admin only)\n"
                           "• /channels - List channels (Admin only)\n"
                           "• /edit_post - Edit existing post (Admin only)\n"
                           "• /add_admin - Add new admin (Owner only)\n"
                           "• /del_admin - Remove admin (Owner only)\n"
                           "• /settings - Configure bot (Owner only)",
                    "image": None,
                    "buttons": [
                        [["⬅️ Back to Start", "start"]],
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
                    # Merge loaded data with default structure
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

# Create application with optimized timeouts
application = (Application.builder()
    .token(BOT_TOKEN)
    .read_timeout(10)
    .write_timeout(20)  
    .connect_timeout(15)
    .pool_timeout(15)
    .build())

# Utility functions
def is_admin(user_id: int) -> bool:
    return user_id in db.get_admins()

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

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

def parse_buttons(button_text: str) -> List[List[Dict]]:
    """Parse button text into structured format"""
    buttons = []
    rows = button_text.split('\n')
    
    for row in rows:
        row_buttons = []
        button_pairs = row.split('|')
        
        for pair in button_pairs:
            if '-' in pair:
                text, url = pair.split('-', 1)
                row_buttons.append({"text": text.strip(), "url": url.strip()})
        
        if row_buttons:
            buttons.append(row_buttons)
    
    return buttons

# Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    settings = db.get_settings().start_message
    keyboard = create_inline_keyboard(settings['buttons'])
    
    await update.message.reply_text(
        settings['text'],
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    settings = db.get_settings().help_message
    keyboard = create_inline_keyboard(settings['buttons'])
    
    await update.message.reply_text(
        settings['text'],
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addch command - admin only"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    user_states[update.effective_user.id] = UserState.AWAITING_CHANNEL_FORWARD
    await update.message.reply_text("📨 Please forward any message from the channel you want to add.")

async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /post command - admin only"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    channels = db.get_channels()
    if not channels:
        await update.message.reply_text("❌ No channels added yet. Use /addch to add channels.")
        return
    
    await show_channel_selection(update, context, "post")

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /channels command - admin only"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    await show_channel_list(update, context)

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings command - owner only"""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner access required.")
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Edit Start Text", callback_data="edit_start_text")],
        [InlineKeyboardButton("📝 Edit Help Text", callback_data="edit_help_text")],
        [InlineKeyboardButton("🔘 Edit Start Buttons", callback_data="edit_start_buttons")],
        [InlineKeyboardButton("🔘 Edit Help Buttons", callback_data="edit_help_buttons")],
        [InlineKeyboardButton("⬅️ Back", callback_data="start")]
    ])
    
    await update.message.reply_text(
        "⚙️ **Bot Settings**\n\nConfigure your bot messages and appearance:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_admin command - owner only"""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner access required.")
        return
    
    user_states[update.effective_user.id] = UserState.AWAITING_ADMIN_USERNAME
    await update.message.reply_text("👮 Send the user ID of the new admin:")

async def del_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /del_admin command - owner only"""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner access required.")
        return
    
    user_states[update.effective_user.id] = UserState.AWAITING_DEL_ADMIN_USERNAME
    await update.message.reply_text("🗑️ Send the user ID of the admin to remove:")

# Callback Query Handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
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
                await show_channel_selection_query(query, "post")
        else:
            await query.answer("❌ Admin access required.", show_alert=True)

# Menu display functions
async def show_start_menu(query):
    """Show start menu"""
    settings = db.get_settings().start_message
    keyboard = create_inline_keyboard(settings['buttons'])
    await query.edit_message_text(
        settings['text'],
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def show_help_menu(query):
    """Show help menu"""
    settings = db.get_settings().help_message
    keyboard = create_inline_keyboard(settings['buttons'])
    await query.edit_message_text(
        settings['text'],
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def show_settings_menu(query):
    """Show settings menu"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Edit Start Text", callback_data="edit_start_text")],
        [InlineKeyboardButton("📝 Edit Help Text", callback_data="edit_help_text")],
        [InlineKeyboardButton("🔘 Edit Start Buttons", callback_data="edit_start_buttons")],
        [InlineKeyboardButton("🔘 Edit Help Buttons", callback_data="edit_help_buttons")],
        [InlineKeyboardButton("⬅️ Back", callback_data="start")]
    ])
    
    await query.edit_message_text(
        "⚙️ **Bot Settings**\n\nConfigure your bot messages and appearance:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def show_channels_menu(query):
    """Show channels menu"""
    channels = db.get_channels()
    if not channels:
        await query.edit_message_text("❌ No channels added yet. Use /addch to add channels.")
        return
    
    keyboard_buttons = []
    for channel in list(channels.values())[:10]:  # Show first 10 channels
        keyboard_buttons.append([
            InlineKeyboardButton(f"📢 {channel.title}", callback_data=f"channel_{channel.chat_id}")
        ])
    
    keyboard_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="help")])
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await query.edit_message_text(
        f"📢 **Connected Channels**\n\nTotal: {len(channels)} channels",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def show_admin_controls(query):
    """Show admin controls menu"""
    admins = db.get_admins()
    admin_list = "\n".join([f"• {admin_id}" for admin_id in admins])
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👮 Add Admin", callback_data="add_admin_cmd")],
        [InlineKeyboardButton("🗑️ Remove Admin", callback_data="del_admin_cmd")],
        [InlineKeyboardButton("⬅️ Back", callback_data="help")]
    ])
    
    await query.edit_message_text(
        f"👮 **Admin Controls**\n\nCurrent Admins:\n{admin_list}",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def show_channel_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    """Show channel selection for posting"""
    channels = db.get_channels()
    keyboard_buttons = []
    
    for channel in list(channels.values())[:8]:  # Limit to 8 channels
        keyboard_buttons.append([
            InlineKeyboardButton(f"📢 {channel.title}", callback_data=f"select_channel_{channel.chat_id}")
        ])
    
    keyboard_buttons.append([InlineKeyboardButton("🔍 Search Channel", callback_data="search_channel")])
    keyboard_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await update.message.reply_text(
        "📢 Select a channel to post in:",
        reply_markup=keyboard
    )

async def show_channel_selection_query(query, action: str):
    """Show channel selection for query"""
    channels = db.get_channels()
    keyboard_buttons = []
    
    for channel in list(channels.values())[:8]:
        keyboard_buttons.append([
            InlineKeyboardButton(f"📢 {channel.title}", callback_data=f"select_channel_{channel.chat_id}")
        ])
    
    keyboard_buttons.append([InlineKeyboardButton("🔍 Search Channel", callback_data="search_channel")])
    keyboard_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await query.edit_message_text(
        "📢 Select a channel to post in:",
        reply_markup=keyboard
    )

async def show_channel_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display channel list"""
    channels = db.get_channels()
    if not channels:
        await update.message.reply_text("❌ No channels added yet. Use /addch to add channels.")
        return
    
    channel_list = "\n".join([f"• {channel.title} (ID: {channel.chat_id})" for channel in channels.values()])
    
    await update.message.reply_text(
        f"📢 **Connected Channels**\n\n{channel_list}\n\nTotal: {len(channels)} channels",
        parse_mode=ParseMode.MARKDOWN
    )

# Message Handler
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for various states"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    
    if state == UserState.AWAITING_ADMIN_USERNAME:
        await handle_add_admin(update, text)
    elif state == UserState.AWAITING_DEL_ADMIN_USERNAME:
        await handle_del_admin(update, text)

async def handle_add_admin(update: Update, text: str):
    """Handle adding new admin"""
    user_id = update.effective_user.id
    
    try:
        new_admin_id = int(text)
        if db.add_admin(new_admin_id):
            await update.message.reply_text(f"✅ Successfully added new admin: {new_admin_id}")
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
            await update.message.reply_text(f"✅ Admin removed successfully: {admin_id}")
        else:
            await update.message.reply_text("❌ Admin not found or cannot remove owner.")
    
    except ValueError:
        await update.message.reply_text("❌ Please send a valid user ID (numbers only).")
    
    if user_id in user_states:
        del user_states[user_id]

# Forward Handler
async def forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle forwarded messages for channel addition"""
    user_id = update.effective_user.id
    
    if user_id not in user_states or user_states[user_id] != UserState.AWAITING_CHANNEL_FORWARD:
        return
    
    forwarded_from = update.message.forward_from_chat
    
    if forwarded_from and forwarded_from.type == "channel":
        try:
            # Check if bot is admin in the channel
            chat_member = await context.bot.get_chat_member(forwarded_from.id, context.bot.id)
            
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("⚠️ Bot must be an admin in this channel before adding.")
                return
            
            # Add channel to database
            channel = Channel(
                chat_id=forwarded_from.id,
                title=forwarded_from.title,
                username=getattr(forwarded_from, 'username', '')
            )
            db.add_channel(channel)
            
            del user_states[user_id]
            await update.message.reply_text(f"✅ Channel added successfully: {forwarded_from.title}")
            
        except Exception as e:
            await update.message.reply_text("❌ Error verifying bot admin status. Please try again.")
            logger.error(f"Error checking admin status: {e}")

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
    application.add_handler(MessageHandler(filters.FORWARDED, forward_handler))

# Main function
def main():
    """Main function to run the bot"""
    logger.info("Starting bot with JSON database...")
    
    # Setup all handlers
    setup_handlers()
    
    # Run the bot with polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
