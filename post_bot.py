import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    InputMediaPhoto, InputMediaDocument, Message
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, CallbackContext
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

# Load environment variables
load_dotenv("Bot_Token.env")  # Load variables from .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database models (using dict as example - replace with actual database)
class BotSettings:
    def __init__(self):
        self.start_message = {
            'text': '🤖 Welcome to the Advanced Telegram Bot!\n\nUse the buttons below to navigate:',
            'image': None,
            'buttons': [
                [('🔹 Help', 'help')],
                [('🔹 Add Channel', 'add_channel')],
                [('🔹 Post Panel', 'post_panel')],
                [('🔹 Settings', 'settings')]
            ]
        }
        self.help_message = {
            'text': '📖 **Bot Help Guide**\n\n'
                   '• /start - Start the bot\n'
                   '• /help - Show this help message\n'
                   '• /addch - Add a channel (Admin only)\n'
                   '• /post - Open post panel (Admin only)\n'
                   '• /channels - List channels (Admin only)\n'
                   '• /edit_post - Edit existing post (Admin only)\n'
                   '• /add_admin - Add new admin (Owner only)\n'
                   '• /del_admin - Remove admin (Owner only)\n'
                   '• /settings - Configure bot (Admin only)',
            'image': None,
            'buttons': [
                [('⬅️ Back to Start', 'start')],
                [('⚙️ Settings', 'settings')],
                [('📢 Channel Manager', 'channels')],
                [('👮 Admin Controls', 'admin_controls')]
            ]
        }

class Channel:
    def __init__(self, chat_id: int, title: str, username: str = None):
        self.chat_id = chat_id
        self.title = title
        self.username = username

class PostDraft:
    def __init__(self):
        self.channel_id = None
        self.content = None
        self.buttons = None
        self.message_id = None

class UserState(Enum):
    AWAITING_CHANNEL_FORWARD = "awaiting_channel_forward"
    AWAITING_POST_CONTENT = "awaiting_post_content"
    AWAITING_BUTTONS = "awaiting_buttons"
    AWAITING_CHANNEL_SEARCH = "awaiting_channel_search"
    AWAITING_EDIT_CONTENT = "awaiting_edit_content"
    AWAITING_EDIT_BUTTONS = "awaiting_edit_buttons"
    AWAITING_ADMIN_USERNAME = "awaiting_admin_username"
    AWAITING_DEL_ADMIN_USERNAME = "awaiting_del_admin_username"

# Global storage (replace with proper database)
bot_settings = BotSettings()
channels: Dict[int, Channel] = {}
admins: List[int] = [123456789]  # Add your user ID here
user_states: Dict[int, UserState] = {}
post_drafts: Dict[int, PostDraft] = {}
edit_sessions: Dict[int, Dict] = {}

class BotManager:
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("addch", self.add_channel_command))
        self.application.add_handler(CommandHandler("post", self.post_command))
        self.application.add_handler(CommandHandler("channels", self.channels_command))
        self.application.add_handler(CommandHandler("edit_post", self.edit_post_command))
        self.application.add_handler(CommandHandler("add_admin", self.add_admin_command))
        self.application.add_handler(CommandHandler("del_admin", self.del_admin_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        
        # Callback query handlers
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.FORWARDED, self.forward_handler))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        
        settings = bot_settings.start_message
        keyboard = self.create_inline_keyboard(settings['buttons'])
        
        if settings['image']:
            await update.message.reply_photo(
                photo=settings['image'],
                caption=settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        settings = bot_settings.help_message
        keyboard = self.create_inline_keyboard(settings['buttons'])
        
        if settings['image']:
            await update.message.reply_photo(
                photo=settings['image'],
                caption=settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def add_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addch command - admin only"""
        if not await self.is_admin(update):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        user_states[update.effective_user.id] = UserState.AWAITING_CHANNEL_FORWARD
        await update.message.reply_text(
            "📨 Please forward any message from the channel you want to add."
        )
    
    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /post command - admin only"""
        if not await self.is_admin(update):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        await self.show_channel_selection(update, context, "post")
    
    async def channels_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /channels command - admin only"""
        if not await self.is_admin(update):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        await self.show_channel_list(update, context, page=0)
    
    async def edit_post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /edit_post command - admin only"""
        if not await self.is_admin(update):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        await update.message.reply_text(
            "📝 Forward the post (sent by this bot) that you want to edit."
        )
        user_states[update.effective_user.id] = UserState.AWAITING_CHANNEL_FORWARD
    
    async def add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_admin command - owner only"""
        if not await self.is_owner(update):
            await update.message.reply_text("❌ Owner access required.")
            return
        
        user_states[update.effective_user.id] = UserState.AWAITING_ADMIN_USERNAME
        await update.message.reply_text(
            "👮 Send the username or user ID of the new admin:"
        )
    
    async def del_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /del_admin command - owner only"""
        if not await self.is_owner(update):
            await update.message.reply_text("❌ Owner access required.")
            return
        
        user_states[update.effective_user.id] = UserState.AWAITING_DEL_ADMIN_USERNAME
        await update.message.reply_text(
            "🗑️ Send the username or user ID of the admin to remove:"
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command - admin only"""
        if not await self.is_admin(update):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Edit Start Text", callback_data="edit_start_text")],
            [InlineKeyboardButton("📝 Edit Help Text", callback_data="edit_help_text")],
            [InlineKeyboardButton("🖼️ Change Start Image", callback_data="edit_start_image")],
            [InlineKeyboardButton("🖼️ Change Help Image", callback_data="edit_help_image")],
            [InlineKeyboardButton("🔘 Edit Start Buttons", callback_data="edit_start_buttons")],
            [InlineKeyboardButton("🔘 Edit Help Buttons", callback_data="edit_help_buttons")],
            [InlineKeyboardButton("⬅️ Back", callback_data="start")]
        ])
        
        await update.message.reply_text(
            "⚙️ **Bot Settings**\n\nConfigure your bot messages and appearance:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button clicks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        # Navigation handlers
        if data == "start":
            await self.show_start_menu(query)
        elif data == "help":
            await self.show_help_menu(query)
        elif data == "settings":
            await self.show_settings_menu(query)
        elif data == "channels":
            await self.show_channel_list_query(query, page=0)
        elif data == "admin_controls":
            await self.show_admin_controls(query)
        elif data == "add_channel":
            if await self.is_admin_query(query):
                user_states[user_id] = UserState.AWAITING_CHANNEL_FORWARD
                await query.edit_message_text("📨 Please forward any message from the channel you want to add.")
        elif data == "post_panel":
            if await self.is_admin_query(query):
                await self.show_channel_selection_query(query, "post")
        
        # Channel selection for posting
        elif data.startswith("select_channel_"):
            if await self.is_admin_query(query):
                channel_id = int(data.split("_")[2])
                await self.start_post_draft(query, channel_id)
        
        # Post management
        elif data == "search_channel":
            if await self.is_admin_query(query):
                user_states[user_id] = UserState.AWAITING_CHANNEL_SEARCH
                await query.edit_message_text("🔍 Send the name of the channel you want to post in:")
        elif data == "send_post":
            if await self.is_admin_query(query):
                await self.send_post(query)
        elif data == "cancel_post":
            if await self.is_admin_query(query):
                if user_id in post_drafts:
                    del post_drafts[user_id]
                await query.edit_message_text("❌ Post cancelled.")
        
        # Pagination
        elif data.startswith("page_"):
            page = int(data.split("_")[1])
            await self.show_channel_list_query(query, page)
    
    async def forward_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle forwarded messages for channel addition"""
        user_id = update.effective_user.id
        
        if user_id not in user_states:
            return
        
        state = user_states[user_id]
        
        if state == UserState.AWAITING_CHANNEL_FORWARD:
            forwarded_from = update.message.forward_from_chat
            
            if forwarded_from and forwarded_from.type == "channel":
                # Check if bot is admin in the channel
                try:
                    chat_member = await context.bot.get_chat_member(
                        forwarded_from.id, context.bot.id
                    )
                    
                    if chat_member.status not in ['administrator', 'creator']:
                        await update.message.reply_text(
                            "⚠️ Bot must be an admin in this channel before adding."
                        )
                        return
                    
                    # Add channel to database
                    channel = Channel(
                        chat_id=forwarded_from.id,
                        title=forwarded_from.title,
                        username=forwarded_from.username
                    )
                    channels[forwarded_from.id] = channel
                    
                    del user_states[user_id]
                    await update.message.reply_text(
                        f"✅ Channel added successfully: {forwarded_from.title}"
                    )
                    
                except Exception as e:
                    await update.message.reply_text(
                        "❌ Error verifying bot admin status. Please try again."
                    )
                    logger.error(f"Error checking admin status: {e}")
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages for various states"""
        user_id = update.effective_user.id
        text = update.message.text
        
        if user_id not in user_states:
            return
        
        state = user_states[user_id]
        
        if state == UserState.AWAITING_POST_CONTENT:
            await self.handle_post_content(update, text)
        
        elif state == UserState.AWAITING_BUTTONS:
            await self.handle_post_buttons(update, text)
        
        elif state == UserState.AWAITING_CHANNEL_SEARCH:
            await self.handle_channel_search(update, text)
        
        elif state == UserState.AWAITING_ADMIN_USERNAME:
            await self.handle_add_admin(update, text)
        
        elif state == UserState.AWAITING_DEL_ADMIN_USERNAME:
            await self.handle_del_admin(update, text)
    
    async def handle_post_content(self, update: Update, text: str):
        """Handle post content input"""
        user_id = update.effective_user.id
        
        if user_id in post_drafts:
            post_drafts[user_id].content = text
            user_states[user_id] = UserState.AWAITING_BUTTONS
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Add URL Buttons", callback_data="add_buttons")],
                [InlineKeyboardButton("📤 Send Post", callback_data="send_post")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")]
            ])
            
            await update.message.reply_text(
                "✅ Content saved! Add URL buttons or send the post:",
                reply_markup=keyboard
            )
    
    async def handle_post_buttons(self, update: Update, text: str):
        """Handle URL buttons input"""
        user_id = update.effective_user.id
        
        if user_id in post_drafts:
            try:
                buttons = self.parse_buttons(text)
                post_drafts[user_id].buttons = buttons
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 Send Post", callback_data="send_post")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")]
                ])
                
                await update.message.reply_text(
                    "✅ Buttons added! Ready to send post:",
                    reply_markup=keyboard
                )
                
            except Exception as e:
                await update.message.reply_text(
                    "❌ Invalid button format. Use: ButtonText - url | Button2 - url2"
                )
    
    async def handle_channel_search(self, update: Update, text: str):
        """Handle channel search"""
        user_id = update.effective_user.id
        matching_channels = [
            channel for channel in channels.values() 
            if text.lower() in channel.title.lower()
        ]
        
        if not matching_channels:
            await update.message.reply_text("❌ No channels found with that name.")
            return
        
        keyboard_buttons = []
        for channel in matching_channels[:10]:  # Limit results
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"📢 {channel.title}",
                    callback_data=f"select_channel_{channel.chat_id}"
                )
            ])
        
        keyboard_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="post_panel")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await update.message.reply_text(
            f"🔍 Found {len(matching_channels)} channels:",
            reply_markup=keyboard
        )
        
        del user_states[user_id]
    
    async def handle_add_admin(self, update: Update, text: str):
        """Handle adding new admin"""
        user_id = update.effective_user.id
        
        try:
            # Try to parse as user ID
            new_admin_id = int(text)
            admins.append(new_admin_id)
            await update.message.reply_text(f"✅ Successfully added new admin: {new_admin_id}")
        
        except ValueError:
            # Handle username (without @)
            username = text.lstrip('@')
            # In a real implementation, you'd need to resolve username to user ID
            await update.message.reply_text(
                f"✅ Admin addition for @{username} would be processed (user ID resolution needed)"
            )
        
        del user_states[user_id]
    
    async def handle_del_admin(self, update: Update, text: str):
        """Handle removing admin"""
        user_id = update.effective_user.id
        
        try:
            # Try to parse as user ID
            admin_id = int(text)
            if admin_id in admins:
                admins.remove(admin_id)
                await update.message.reply_text(f"❌ Admin removed successfully: {admin_id}")
            else:
                await update.message.reply_text("❌ Admin not found.")
        
        except ValueError:
            # Handle username
            username = text.lstrip('@')
            await update.message.reply_text(
                f"✅ Admin removal for @{username} would be processed (user ID resolution needed)"
            )
        
        del user_states[user_id]
    
    async def show_channel_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
        """Show channel selection for posting"""
        await self.show_channel_list(update, context, page=0, action=action)
    
    async def show_channel_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0, action: str = "post"):
        """Display paginated channel list"""
        if not channels:
            await update.message.reply_text("❌ No channels added yet. Use /addch to add channels.")
            return
        
        channel_list = list(channels.values())
        items_per_page = 8
        total_pages = (len(channel_list) + items_per_page - 1) // items_per_page
        
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(channel_list))
        
        keyboard_buttons = []
        for channel in channel_list[start_idx:end_idx]:
            if action == "post":
                callback_data = f"select_channel_{channel.chat_id}"
            else:
                callback_data = f"channel_info_{channel.chat_id}"
            
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"📢 {channel.title}",
                    callback_data=callback_data
                )
            ])
        
        # Pagination controls
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⏮ Back", callback_data=f"page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ⏭", callback_data=f"page_{page+1}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
        
        # Action buttons
        action_buttons = [
            InlineKeyboardButton("🔍 Search", callback_data="search_channel"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
        keyboard_buttons.append(action_buttons)
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        text = f"📢 **Connected Channels**\n\nPage {page + 1}/{total_pages}\nSelect a channel:"
        
        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    async def start_post_draft(self, query, channel_id: int):
        """Start a new post draft"""
        user_id = query.from_user.id
        
        if channel_id not in channels:
            await query.answer("❌ Channel not found.", show_alert=True)
            return
        
        post_drafts[user_id] = PostDraft()
        post_drafts[user_id].channel_id = channel_id
        user_states[user_id] = UserState.AWAITING_POST_CONTENT
        
        channel = channels[channel_id]
        await query.edit_message_text(
            f"✏️ Now send me the text, media, or any content you want to post in {channel.title}."
        )
    
    async def send_post(self, query):
        """Send the post to the channel"""
        user_id = query.from_user.id
        
        if user_id not in post_drafts:
            await query.answer("❌ No post draft found.", show_alert=True)
            return
        
        draft = post_drafts[user_id]
        channel_id = draft.channel_id
        
        if channel_id not in channels:
            await query.answer("❌ Channel not found.", show_alert=True)
            return
        
        try:
            keyboard = None
            if draft.buttons:
                keyboard = self.create_inline_keyboard(draft.buttons)
            
            # Send the post
            message = await query.bot.send_message(
                chat_id=channel_id,
                text=draft.content,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            draft.message_id = message.message_id
            
            await query.edit_message_text(
                f"✅ Post sent successfully to {channels[channel_id].title}!"
            )
            
            # Clean up
            del post_drafts[user_id]
            if user_id in user_states:
                del user_states[user_id]
                
        except Exception as e:
            logger.error(f"Error sending post: {e}")
            await query.answer("❌ Error sending post. Check bot permissions.", show_alert=True)
    
    def parse_buttons(self, button_text: str) -> List[List[Tuple[str, str]]]:
        """Parse button text into structured format"""
        buttons = []
        rows = button_text.split('\n')
        
        for row in rows:
            row_buttons = []
            button_pairs = row.split('|')
            
            for pair in button_pairs:
                if '-' in pair:
                    text, url = pair.split('-', 1)
                    row_buttons.append((text.strip(), url.strip()))
            
            if row_buttons:
                buttons.append(row_buttons)
        
        return buttons
    
    def create_inline_keyboard(self, buttons_config: List[List[Tuple[str, str]]]) -> InlineKeyboardMarkup:
        """Create inline keyboard from button configuration"""
        keyboard = []
        
        for row in buttons_config:
            keyboard_row = []
            for button_text, callback_data in row:
                keyboard_row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            keyboard.append(keyboard_row)
        
        return InlineKeyboardMarkup(keyboard)
    
    async def is_admin(self, update: Update) -> bool:
        """Check if user is admin"""
        return update.effective_user.id in admins
    
    async def is_admin_query(self, query) -> bool:
        """Check if user is admin for query"""
        if query.from_user.id not in admins:
            await query.answer("❌ Admin access required.", show_alert=True)
            return False
        return True
    
    async def is_owner(self, update: Update) -> bool:
        """Check if user is owner (first admin)"""
        return update.effective_user.id == admins[0] if admins else False
    
    async def show_start_menu(self, query):
        """Show start menu"""
        settings = bot_settings.start_message
        keyboard = self.create_inline_keyboard(settings['buttons'])
        
        if settings['image']:
            await query.edit_message_media(
                media=InputMediaPhoto(settings['image'], caption=settings['text']),
                reply_markup=keyboard
            )
        else:
            await query.edit_message_text(
                settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def show_help_menu(self, query):
        """Show help menu"""
        settings = bot_settings.help_message
        keyboard = self.create_inline_keyboard(settings['buttons'])
        
        if settings['image']:
            await query.edit_message_media(
                media=InputMediaPhoto(settings['image'], caption=settings['text']),
                reply_markup=keyboard
            )
        else:
            await query.edit_message_text(
                settings['text'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def show_settings_menu(self, query):
        """Show settings menu"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Edit Start Text", callback_data="edit_start_text")],
            [InlineKeyboardButton("📝 Edit Help Text", callback_data="edit_help_text")],
            [InlineKeyboardButton("🖼️ Change Start Image", callback_data="edit_start_image")],
            [InlineKeyboardButton("🖼️ Change Help Image", callback_data="edit_help_image")],
            [InlineKeyboardButton("🔘 Edit Start Buttons", callback_data="edit_start_buttons")],
            [InlineKeyboardButton("🔘 Edit Help Buttons", callback_data="edit_help_buttons")],
            [InlineKeyboardButton("⬅️ Back", callback_data="start")]
        ])
        
        await query.edit_message_text(
            "⚙️ **Bot Settings**\n\nConfigure your bot messages and appearance:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_admin_controls(self, query):
        """Show admin controls menu"""
        if not await self.is_admin_query(query):
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👮 Add Admin", callback_data="add_admin_cmd")],
            [InlineKeyboardButton("🗑️ Remove Admin", callback_data="del_admin_cmd")],
            [InlineKeyboardButton("⬅️ Back", callback_data="help")]
        ])
        
        await query.edit_message_text(
            "👮 **Admin Controls**\n\nManage bot administrators:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_channel_list_query(self, query, page: int = 0):
        """Show channel list for query"""
        await self.show_channel_list(None, query, page=page)
async def show_channel_selection_query(self, query, action: str):
        """Show channel selection for query"""
        await self.show_channel_list(None, query, page=0, action=action)
    
async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again later."
            )
# Create application with your specified timeouts
application = (Application.builder()
    .token(BOT_TOKEN)
    .read_timeout(15)
    .write_timeout(30)  
    .connect_timeout(20)
    .pool_timeout(20)
    .build())

async def run():
    """Start the bot with your specified running process"""
    await load_admin_ids()
    logger.info("Bot started successfully!")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Keep connection alive with shorter intervals for Termux  
    if hasattr(application.updater, 'job_queue') and hasattr(application.updater.job_queue, 'scheduler'):
        application.updater.job_queue.scheduler.configure(
            timezone="UTC",
            max_workers=2  # Reduce worker threads for Termux
        )

def main():
    """Main function to run the bot"""
    import asyncio
    
    try:
        # Start the bot
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error starting bot: {e}")

if __name__ == "__main__":
    main()
