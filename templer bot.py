# ===----------------------------------------------------------------------=== #
#          Simplified Telegram File Share Bot (No Membership Check)            #
#                        (With Keep-Alive)                                   #
# ===----------------------------------------------------------------------=== #

# 1. Environment Variable Loading (MUST be at the very top)
import os
from dotenv import load_dotenv
load_dotenv() # Loads .env file if present (for local testing), platform env vars take precedence

# 2. Keep Alive Import
from keep_alive import keep_alive # Assuming keep_alive.py is in the same directory

# 3. Standard Imports
import logging
import asyncio
from telegram import (
    Update,
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    JobQueue,
    Defaults,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError, Forbidden, BadRequest
from telegram.helpers import escape_markdown # For MarkdownV2 escaping

# === Logging Setup ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING) # For Flask's server
logger = logging.getLogger(__name__)

# === Configuration ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME')
PRIVATE_CHANNEL_ID = os.getenv('PRIVATE_CHANNEL_ID') # For reference
PUBLIC_CHANNEL_ID_STR = os.getenv('PUBLIC_CHANNEL_ID')

PUBLIC_CHANNEL_ID = None
if PUBLIC_CHANNEL_ID_STR:
    try:
        PUBLIC_CHANNEL_ID = int(PUBLIC_CHANNEL_ID_STR) if PUBLIC_CHANNEL_ID_STR.startswith('-') and PUBLIC_CHANNEL_ID_STR[1:].isdigit() else PUBLIC_CHANNEL_ID_STR
    except (ValueError, TypeError):
        logger.error(f"PUBLIC_CHANNEL_ID ('{PUBLIC_CHANNEL_ID_STR}') is not valid. Bot might not function correctly.")
        PUBLIC_CHANNEL_ID = PUBLIC_CHANNEL_ID_STR # Keep as string if conversion fails
else:
    logger.critical("CRITICAL ERROR: PUBLIC_CHANNEL_ID is not set in the environment.")

if not BOT_TOKEN: logger.critical("CRITICAL ERROR: BOT_TOKEN is not set.")
if not BOT_USERNAME: logger.warning("WARNING: BOT_USERNAME is not set. Deep links for buttons might be incorrect.")
# PUBLIC_CHANNEL_ID check already done

# --- File & Series/Season Configuration ---
SEASONS = {
    'apothecary_diaries_s1': [ # Using underscores for keys is better for URLs
        'BQACAgQAAxkBAAEBEWhoImGp0GLWjLBTaJ90ZcIYtdFtvQACtSMAA1AZUQABXCxSF360SzYE',
        'BQACAgQAAxkBAAEBEX9oInhdz1T_S7sJEifWD91VL5vO7QACzyMAA1AZUZ107KoTZlUXNgQ',
        'BQACAgQAAxkBAAEBFY5oIyNYobHZHWWk2DJ2Hjkx99LgRAAC1CMAA1AZUdl6cVfp1NJENgQ',
        'BQACAgQAAxkBAAEBFZRoIyPO_rPhGaOyzbrB9C1i0kVQFAAC2CMAA1AZUdTTQh9FDanpNgQ',
        'BQACAgQAAxkBAAEBFZ5oIyRnTpQuMZmUL6G0WhoO5B4aTAAC7CMAA1AZUbD3Pqh5iI1gNgQ',
        'BQACAgQAAxkBAAEBFaRoIyUvMwXAz9PJcwM1IppLokbTxwAC_iMAA1AZUa4d5x39FGS6NgQ',
        'BQACAgQAAxkBAAEBFapoIyWcR6Le331xB_Hy3e3yyLuNlwAC_yMAA1AZUSGVkYFzvP5GNgQ',
        'BQACAgQAAxkBAAEBFa5oIyXqcbLkpRD8H0JIea1iQcBN9QACASQAA1AZUQIF8Id9ze3tNgQ',
        'BQACAgQAAxkBAAEBFbBoIyYNu-Oz0H_CmwSiouSiq2WESAACAyQAA1AZUZlu2B38psTBNgQ',
        'BQACAgQAAxkBAAEBFbJoIyY5Y0wmYpBtM6pl9f4HNN6XzwACBSQAA1AZUeb9OVa0RYU1NgQ',
        'BQACAgQAAxkBAAEBFbdoIyaq6xhaL0IQieSe4wakJd5WiQACBiQAA1AZUbUJS4dMKZIKNgQ',
        'BQACAgQAAxkBAAEBFbloIybcbew4-C-ALKSiyYbX0LvZzQACByQAA1AZUcm08Upui6CaNgQ',
        'BQACAgQAAxkBAAEBFcxoIyfdR-Q4uWTvvCYYJRK1vX129AACCCQAA1AZUUUV06vwTECfNgQ',
        'BQACAgQAAxkBAAEBFcxoIyfdR-Q4uWTvvCYYJRK1vX129AACCCQAA1AZUUUV06vwTECfNgQ',
        'BQACAgQAAxkBAAEBFdRoIyhfAWiiAUhdtrryj7NOjFW8pwACCiQAA1AZUfPBIAQINEVLNgQ',
        'BQACAgQAAxkBAAEBFdhoIyiVNqJxHKEkceFyPylG5vH0ugACCyQAA1AZUat5zS5woEANNgQ',
    ],
    'another_series_s2': [ # Example, populate with real IDs
        'FILE_ID_S02E01',
        'FILE_ID_S02E02',
    ],
}

SEASONS_DISPLAY_NAMES = { # For prettier button text
    'apothecary_diaries_s1': "Apothecary Diaries (S1 Dual 1080p)",
    'another_series_s2': "Another Series (Season 2)",
}

DELETE_AFTER_SECONDS = 20 * 60
AUTO_SETUP_BUTTONS_ON_START = True

# === Core Bot Logic ===

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command, primarily processing deep links."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    args = context.args

    if not PUBLIC_CHANNEL_ID: # This check can remain for the welcome message
        logger.error("start_handler: PUBLIC_CHANNEL_ID is not configured.")
        if update.message: await update.message.reply_text("Bot configuration error. Please contact admin.", parse_mode=None)
        return

    logger.info(f"/start command: user={user.id}({user.full_name or 'UnknownUser'}), chat={chat_id}, args={args}")

    if not args:
        pc_id_display = str(PUBLIC_CHANNEL_ID)
        if isinstance(PUBLIC_CHANNEL_ID, str) and PUBLIC_CHANNEL_ID.startswith('@'):
             pc_id_display = escape_markdown(PUBLIC_CHANNEL_ID, version=2)
        await update.message.reply_text(
            f"Hello\\! 👋 Please use the buttons in our public channel ({pc_id_display}) to request files\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Sent welcome message to user {user.id} (no deep link args).")
        return

    content_key = args[0].lower()

    if content_key not in SEASONS:
        await update.message.reply_text("😕 Sorry, I don't recognize that request key. Please ensure you clicked a valid button from the channel.", parse_mode=None)
        logger.warning(f"User {user.id} requested unknown key: '{content_key}'.")
        return

    file_ids = SEASONS.get(content_key, [])
    valid_file_ids = [fid for fid in file_ids if fid and not fid.startswith('FILE_ID_')]
    display_content_name = SEASONS_DISPLAY_NAMES.get(content_key, content_key.replace('_', ' ').title())

    if not valid_file_ids:
        await update.message.reply_text(
            f"🚧 Files for '{escape_markdown(display_content_name, version=2)}' seem to be missing or not configured correctly yet\\. "
            "Please check back later or contact an admin\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"No valid file IDs found for key '{content_key}' requested by user {user.id}.")
        return

    await update.message.reply_text(
        f"✅ Got it\\! Sending you {len(valid_file_ids)} file\\(s\\) for '{escape_markdown(display_content_name, version=2)}'\\.\n\n"
        f"🕒 _These files will be automatically deleted in {DELETE_AFTER_SECONDS // 60} minutes\\._",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    logger.info(f"Processing request for '{content_key}' ({len(valid_file_ids)} files) for user {user.id}.")

    sent_count = 0
    failed_count = 0
    for index, file_id in enumerate(valid_file_ids):
        try:
            caption = f"{display_content_name} - Part {index + 1}" # Captions are plain text by default
            sent_message = await context.bot.send_document(
                chat_id=chat_id,
                document=file_id,
                caption=caption,
            )
            sent_count += 1
            logger.info(f"Successfully sent file {index + 1}/{len(valid_file_ids)} (ID: ...{file_id[-10:]}) for '{content_key}' to user {user.id}.")

            context.job_queue.run_once(
                delete_message_job,
                when=DELETE_AFTER_SECONDS,
                data={'chat_id': chat_id, 'message_id': sent_message.message_id},
                name=f'del_{chat_id}_{sent_message.message_id}'
            )
            logger.info(f"Scheduled message {sent_message.message_id} for deletion in {DELETE_AFTER_SECONDS}s.")
            await asyncio.sleep(0.5) # Polite delay

        except Forbidden as e:
            failed_count += 1
            logger.error(f"Forbidden error sending file Part {index+1} ('{content_key}') for {user.id}: {e}.")
            if failed_count == 1: await context.bot.send_message(chat_id, "⚠️ I couldn't send one or more files. I might be blocked or lack permissions.", parse_mode=None)
        except BadRequest as e:
             failed_count += 1
             logger.error(f"BadRequest error sending file Part {index+1} ('{content_key}') for {user.id}: {e}.")
             if "FILE_ID_INVALID" in str(e).upper() and failed_count == 1:
                 await context.bot.send_message(chat_id, f"⚠️ Couldn't send file {index + 1}. The file ID seems invalid or the file was removed.", parse_mode=None)
             elif failed_count == 1:
                 await context.bot.send_message(chat_id, f"⚠️ Couldn't send file {index + 1} due to a request error.", parse_mode=None)
        except TelegramError as e:
            failed_count += 1
            logger.error(f"Telegram error sending file Part {index+1} ('{content_key}') for {user.id}: {e}")
            if failed_count == 1: await context.bot.send_message(chat_id, f"⚠️ An error occurred while sending file {index + 1}. Please try again later.", parse_mode=None)
        except Exception as e:
            failed_count += 1
            logger.exception(f"Unexpected error sending file Part {index+1} ('{content_key}') for {user.id}: {e}")
            if failed_count == 1: await context.bot.send_message(chat_id, f"⚠️ An unexpected error occurred sending file {index + 1}.", parse_mode=None)

    if failed_count > 0:
         logger.warning(f"Finished sending for '{content_key}' to user {user.id}. Sent: {sent_count}, Failed: {failed_count}.")
    else:
         logger.info(f"Successfully sent all {sent_count} files for '{content_key}' to user {user.id}.")


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job; chat_id = job.data['chat_id']; message_id = job.data['message_id']
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully auto-deleted message {message_id} from chat {chat_id}.")
    except Forbidden: logger.warning(f"No permission to auto-delete message {message_id} in chat {chat_id}.")
    except BadRequest as e:
        if "message to delete not found" in str(e).lower() or "message_id_invalid" in str(e).lower():
            logger.info(f"Message {message_id} in chat {chat_id} already deleted or invalid.")
        else: logger.warning(f"BadRequest when deleting message {message_id} in chat {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during auto-deletion of message {message_id} in chat {chat_id}: {e}", exc_info=True)


async def setup_buttons(context: ContextTypes.DEFAULT_TYPE = None, bot: Bot = None):
    if not bot and context: bot = context.bot
    if not bot: logger.error("setup_buttons: Bot instance missing."); return
    if not PUBLIC_CHANNEL_ID or not BOT_USERNAME:
        logger.error("setup_buttons: Crucial configuration (PUBLIC_CHANNEL_ID or BOT_USERNAME) missing.")
        return

    keyboard = []
    if not SEASONS: logger.warning("setup_buttons: SEASONS dictionary is empty."); return
    
    valid_keys = sorted([k for k, v_list in SEASONS.items() if any(fid and not fid.startswith('FILE_ID_') for fid in v_list)])
    if not valid_keys: logger.warning("setup_buttons: No valid content keys found with actual file IDs."); return

    for key in valid_keys:
        display_name = SEASONS_DISPLAY_NAMES.get(key, key.replace('_', ' ').title())
        button_text = f"🎬 {display_name}"
        button_url = f"https://t.me/{BOT_USERNAME}?start={key}"
        keyboard.append([InlineKeyboardButton(button_text, url=button_url)])

    if not keyboard: logger.error("setup_buttons: Keyboard generation failed unexpectedly."); return
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    safe_bot_username = escape_markdown(BOT_USERNAME, version=2) if BOT_USERNAME else "the bot"
    
    text_lines = [
        "✨ *Welcome to the File Portal\\!* ✨", # Use asterisk for bold in MDv2
        "",
        "Select the content you'd like to receive below\\.",
        # Removed the explicit membership requirement line for this simpler version
        f"Files are sent via @{safe_bot_username} and auto\\-delete after {DELETE_AFTER_SECONDS // 60} minutes\\."
    ]
    text = "\n".join(text_lines)

    try:
        await bot.send_message(
            chat_id=PUBLIC_CHANNEL_ID, text=text, reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
        )
        logger.info(f"Button message sent/updated in channel {PUBLIC_CHANNEL_ID}.")
    except Exception as e:
        logger.error(f"Failed to send button message to {PUBLIC_CHANNEL_ID}: {e}", exc_info=True)
        if "parse" in str(e).lower(): logger.error(f"Problematic MarkdownV2 text for buttons was: {text}")


async def get_chat_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    chat_id_val = chat.id if chat else "N/A" # Use a different name for chat_id to avoid conflict if chat is None
    chat_type_val = chat.type if chat else "N/A"
    user_id_val = user.id if user else "N/A"

    response_text = f"Chat ID: {chat_id_val}\nChat Type: {chat_type_val}"
    if user: response_text += f"\nYour User ID: {user_id_val}"
    logger.info(f"/chatid by user {user_id_val} in chat {chat_id_val} (type: {chat_type_val}).")
    await update.message.reply_text(response_text, parse_mode=None) # Send as plain text


async def post_init_hook(application: Application):
    logger.info("Running post-initialization tasks...")
    if not all([BOT_TOKEN, BOT_USERNAME, PUBLIC_CHANNEL_ID]): # Check for None or empty strings
        logger.warning("post_init: Some critical configurations (BOT_TOKEN, BOT_USERNAME, PUBLIC_CHANNEL_ID) are missing or empty. Bot functionality might be impaired.")

    try:
        bot_info = await application.bot.get_me()
        actual_bot_username = bot_info.username
        logger.info(f"Bot successfully initialized with Telegram: @{actual_bot_username} (ID: {bot_info.id})")
        if BOT_USERNAME and BOT_USERNAME != actual_bot_username: # Check if BOT_USERNAME is not None/empty
             logger.warning(f"CONFIG MISMATCH: Env BOT_USERNAME ('{BOT_USERNAME}') vs actual bot username ('{actual_bot_username}')!")
    except Exception as e:
         logger.error(f"Failed to get bot info during post_init: {e}", exc_info=True)

    if AUTO_SETUP_BUTTONS_ON_START:
        if PUBLIC_CHANNEL_ID and BOT_USERNAME: # Ensure these are not None/empty
             logger.info("post_init: Scheduling button setup for public channel...")
             application.job_queue.run_once(lambda ctx: setup_buttons(bot=application.bot), when=2)
        else:
            logger.error("post_init: Cannot auto-setup buttons; PUBLIC_CHANNEL_ID or BOT_USERNAME is not set/empty in environment.")
    else:
        logger.info("post_init: Automatic button setup on startup is disabled (AUTO_SETUP_BUTTONS_ON_START=False).")

# === Main Bot Execution Function ===
def run_telegram_bot_application():
    logger.info("Attempting to start Telegram bot application...")
    if not BOT_TOKEN: # Critical check for the token
        logger.critical("CRITICAL ERROR: BOT_TOKEN is not set in environment. Telegram bot cannot start.")
        return

    if not SEASONS: logger.warning("WARNING: SEASONS dictionary is empty.")
    elif all(not fid or fid.startswith('FILE_ID_') for sf_list in SEASONS.values() for fid in sf_list if isinstance(sf_list, list)):
         logger.warning("WARNING: SEASONS dictionary only contains placeholders or empty lists of files.")

    defaults = Defaults(parse_mode=ParseMode.MARKDOWN_V2) # Set default parse mode
    
    try:
        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .defaults(defaults)
            .job_queue(JobQueue())
            .post_init(post_init_hook)
            .build()
        )
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to build Telegram application. Error: {e}", exc_info=True)
        return

    logger.info("--- Bot Configuration Summary ---")
    logger.info(f"Bot Username (from env): @{BOT_USERNAME or 'NOT SET'}")
    logger.info(f"Public Channel (from env): {PUBLIC_CHANNEL_ID or 'NOT SET'}")
    logger.info(f"Private Channel ID (from env, ref): {PRIVATE_CHANNEL_ID or 'NOT SET'}")
    logger.info(f"Defined Content Keys: {list(SEASONS.keys())}")
    logger.info(f"Auto-delete files after: {DELETE_AFTER_SECONDS} seconds")
    logger.info(f"Auto-setup buttons on start: {AUTO_SETUP_BUTTONS_ON_START}")
    logger.info("--------------------------------")

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("chatid", get_chat_id_handler))
    # No CallbackQueryHandler for retry_handler in this version

    logger.info("Starting Telegram bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Telegram bot polling stopped.")

# === Main Entry Point ===
if __name__ == '__main__':
    logger.info("Script execution starting...")

    if not all([BOT_TOKEN, BOT_USERNAME, PUBLIC_CHANNEL_ID]):
        logger.critical("CRITICAL ERROR: BOT_TOKEN, BOT_USERNAME, or PUBLIC_CHANNEL_ID is missing from environment. Bot may not run reliably. Please check configuration (e.g., .env file or platform environment variables).")
        # import sys; sys.exit(1) # Optional: Force exit if criticals are missing
    else:
        logger.info("Essential configurations (BOT_TOKEN, BOT_USERNAME, PUBLIC_CHANNEL_ID) appear to be loaded.")
        
        try:
            keep_alive() # Start the keep-alive Flask server (non-blocking thread)
            logger.info("Keep_alive server thread initiated.")
        except Exception as e_ka:
            logger.error(f"Could not start keep_alive server: {e_ka}", exc_info=True)
        
        try:
            run_telegram_bot_application()
        except KeyboardInterrupt:
            logger.info("Bot process stopped by user (Ctrl+C).")
        except Exception as e_main_bot:
            logger.critical(f"UNHANDLED EXCEPTION in main bot execution scope: {e_main_bot}", exc_info=True)

    logger.info("Script execution finished or bot has been stopped.")
