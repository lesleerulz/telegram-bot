# ===----------------------------------------------------------------------=== #
#          Simplified Telegram File Share Bot (No Membership Check)            #
#                        (With Keep-Alive & MDv2 Fix)                         #
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
from telegram.constants import ParseMode # No ChatMemberStatus needed for this version
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
    'apothecary_diaries_s1': [
        'BQACAgQAAxkBAAEBEWhoImGp0GLWjLBTaJ90ZcIYtdFtvQACtSMAA1AZUQABXCxSF360SzYE', 'BQACAgQAAxkBAAEBEX9oInhdz1T_S7sJEifWD91VL5vO7QACzyMAA1AZUZ107KoTZlUXNgQ',
        'BQACAgQAAxkBAAEBFY5oIyNYobHZHWWk2DJ2Hjkx99LgRAAC1CMAA1AZUdl6cVfp1NJENgQ', 'BQACAgQAAxkBAAEBFZRoIyPO_rPhGaOyzbrB9C1i0kVQFAAC2CMAA1AZUdTTQh9FDanpNgQ',
        'BQACAgQAAxkBAAEBFZ5oIyRnTpQuMZmUL6G0WhoO5B4aTAAC7CMAA1AZUbD3Pqh5iI1gNgQ', 'BQACAgQAAxkBAAEBFaRoIyUvMwXAz9PJcwM1IppLokbTxwAC_iMAA1AZUa4d5x39FGS6NgQ',
        'BQACAgQAAxkBAAEBFapoIyWcR6Le331xB_Hy3e3yyLuNlwAC_yMAA1AZUSGVkYFzvP5GNgQ', 'BQACAgQAAxkBAAEBFa5oIyXqcbLkpRD8H0JIea1iQcBN9QACASQAA1AZUQIF8Id9ze3tNgQ',
        'BQACAgQAAxkBAAEBFbBoIyYNu-Oz0H_CmwSiouSiq2WESAACAyQAA1AZUZlu2B38psTBNgQ', 'BQACAgQAAxkBAAEBFbJoIyY5Y0wmYpBtM6pl9f4HNN6XzwACBSQAA1AZUeb9OVa0RYU1NgQ',
        'BQACAgQAAxkBAAEBFbdoIyaq6xhaL0IQieSe4wakJd5WiQACBiQAA1AZUbUJS4dMKZIKNgQ', 'BQACAgQAAxkBAAEBFbloIybcbew4-C-ALKSiyYbX0LvZzQACByQAA1AZUcm08Upui6CaNgQ',
        'BQACAgQAAxkBAAEBFcxoIyfdR-Q4uWTvvCYYJRK1vX129AACCCQAA1AZUUUV06vwTECfNgQ', 'BQACAgQAAxkBAAEBFcxoIyfdR-Q4uWTvvCYYJRK1vX129AACCCQAA1AZUUUV06vwTECfNgQ',
        'BQACAgQAAxkBAAEBFdRoIyhfAWiiAUhdtrryj7NOjFW8pwACCiQAA1AZUfPBIAQINEVLNgQ', 
        'BQACAgQAAxkBAAEBFdhoIyiVNqJxHKEkceFyPylG5vH0ugACCyQAA1AZUat5zS5woEANNgQ',
    ],
    'another_series_s2': [ 
        'FILE_ID_S02E01',
        'FILE_ID_S02E02',
    ],
}

SEASONS_DISPLAY_NAMES = { 
    'apothecary_diaries_s1': "Apothecary Diaries (S1 Dual 1080p)",
    'another_series_s2': "Another Series (Season 2)",
}

DELETE_AFTER_SECONDS = 20 * 60
AUTO_SETUP_BUTTONS_ON_START = True

# === Core Bot Logic ===

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    args = context.args

    if not PUBLIC_CHANNEL_ID:
        logger.error("start_handler: PUBLIC_CHANNEL_ID is not configured.")
        if update.message: await update.message.reply_text("Bot configuration error. Please contact admin.", parse_mode=None)
        return

    logger.info(f"/start command: user={user.id}({user.full_name or 'UnknownUser'}), chat={chat_id}, args={args}")

    if not args:
        pc_id_display_escaped = escape_markdown(str(PUBLIC_CHANNEL_ID), version=2)
        if isinstance(PUBLIC_CHANNEL_ID, str) and PUBLIC_CHANNEL_ID.startswith('@'):
             pc_id_display_escaped = escape_markdown(PUBLIC_CHANNEL_ID, version=2) # Usernames are usually safe but doesn't hurt
        
        await update.message.reply_text(
            f"Hello\\! 👋 Please use the buttons in our public channel ({pc_id_display_escaped}) to request files\\.",
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
    escaped_display_name = escape_markdown(display_content_name, version=2) # Escape for use in MarkdownV2

    if not valid_file_ids:
        msg_text = (
            f"🚧 Files for '{escaped_display_name}' seem to be missing or not configured correctly yet\\. "
            "Please check back later or contact an admin\\."
        )
        await update.message.reply_text(msg_text, parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"No valid file IDs found for key '{content_key}' requested by user {user.id}.")
        return

    # *** MODIFIED MESSAGE SENDING FOR CLARITY AND CORRECT ESCAPING ***
    line1 = f"✅ Got it\\! Sending you {len(valid_file_ids)} file\\(s\\) for '{escaped_display_name}'\\."
    line2 = f"🕒 _These files will be automatically deleted in {DELETE_AFTER_SECONDS // 60} minutes\\._"
    full_message = f"{line1}\n\n{line2}"

    try:
        await update.message.reply_text(
            full_message,
            parse_mode=ParseMode.MARKDOWN_V2 # Application default is already this, but being explicit
        )
    except BadRequest as e_msg:
        logger.error(f"BadRequest sending info message for '{content_key}': {e_msg}")
        logger.error(f"Problematic message text that caused error: {full_message}") # Log the exact text
        # Fallback to plain text if MarkdownV2 fails
        plain_message = (
            f"Got it! Sending you {len(valid_file_ids)} file(s) for '{display_content_name}'.\n\n"
            f"These files will be automatically deleted in {DELETE_AFTER_SECONDS // 60} minutes."
        )
        await update.message.reply_text(plain_message, parse_mode=None)
    
    logger.info(f"Processing request for '{content_key}' ({len(valid_file_ids)} files) for user {user.id}.")

    sent_count = 0
    failed_count = 0
    for index, file_id in enumerate(valid_file_ids):
        try:
            caption = f"{display_content_name} - Part {index + 1}"
            sent_message = await context.bot.send_document(
                chat_id=chat_id, document=file_id, caption=caption,
                # If captions ever need Markdown, add: parse_mode=ParseMode.MARKDOWN_V2
            )
            sent_count += 1
            logger.info(f"Successfully sent Part {index + 1} for '{content_key}' to {user.id} (MsgID: {sent_message.message_id}).")
            context.job_queue.run_once(
                delete_message_job, DELETE_AFTER_SECONDS,
                data={'chat_id': chat_id, 'message_id': sent_message.message_id},
                name=f'del_{chat_id}_{sent_message.message_id}'
            )
            await asyncio.sleep(0.5)
        except Forbidden as e:
            failed_count += 1; logger.error(f"Forbidden: Part {index+1} ('{content_key}') for {user.id}: {e}.")
            if failed_count == 1: await context.bot.send_message(chat_id, "⚠️ Couldn't send files. I might be blocked or lack permissions.", parse_mode=None)
        except BadRequest as e:
            failed_count += 1; logger.error(f"BadRequest: Part {index+1} ('{content_key}') for {user.id}: {e}.")
            if "FILE_ID_INVALID" in str(e).upper() and failed_count == 1:
                await context.bot.send_message(chat_id, f"⚠️ Couldn't send file {index+1} (invalid ID or removed).", parse_mode=None)
            elif failed_count == 1:
                await context.bot.send_message(chat_id, f"⚠️ Couldn't send file {index+1} (request error).", parse_mode=None)
        except TelegramError as e:
            failed_count += 1; logger.error(f"TelegramError: Part {index+1} ('{content_key}') for {user.id}: {e}")
            if failed_count == 1: await context.bot.send_message(chat_id, f"⚠️ Error sending file {index+1}. Try again.", parse_mode=None)
        except Exception as e:
            failed_count += 1; logger.exception(f"Unexpected error sending Part {index+1} ('{content_key}') for {user.id}: {e}")
            if failed_count == 1: await context.bot.send_message(chat_id, f"⚠️ Unexpected error sending file {index+1}.", parse_mode=None)

    if failed_count > 0: logger.warning(f"Finished '{content_key}' for {user.id}. Sent: {sent_count}, Failed: {failed_count}.")
    else: logger.info(f"All {sent_count} files for '{content_key}' sent to {user.id}.")


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job; chat_id = job.data['chat_id']; message_id = job.data['message_id']
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Auto-deleted msg {message_id} from chat {chat_id}.")
    except Forbidden: logger.warning(f"No permission to auto-delete {message_id} in {chat_id}.")
    except BadRequest as e:
        if "not found" in str(e).lower() or "invalid" in str(e).lower(): logger.info(f"Msg {message_id} in {chat_id} already deleted/invalid.")
        else: logger.warning(f"BadRequest deleting {message_id} in {chat_id}: {e}")
    except Exception as e: logger.error(f"Err auto-deleting {message_id} in {chat_id}: {e}", exc_info=True)


async def setup_buttons(context: ContextTypes.DEFAULT_TYPE = None, bot: Bot = None):
    if not bot and context: bot = context.bot
    if not bot: logger.error("setup_buttons: Bot missing."); return
    if not PUBLIC_CHANNEL_ID or not BOT_USERNAME: logger.error("setup_buttons: Config missing."); return

    keyboard = []
    if not SEASONS: logger.warning("setup_buttons: SEASONS empty."); return
    valid_keys = sorted([k for k, v_list in SEASONS.items() if any(fid and not fid.startswith('FILE_ID_') for fid in v_list)])
    if not valid_keys: logger.warning("setup_buttons: No valid content keys."); return

    for key in valid_keys:
        display_name = SEASONS_DISPLAY_NAMES.get(key, key.replace('_', ' ').title())
        button_text = f"🎬 {display_name}"
        button_url = f"https://t.me/{BOT_USERNAME}?start={key}"
        keyboard.append([InlineKeyboardButton(button_text, url=button_url)])

    if not keyboard: logger.error("setup_buttons: Keyboard gen failed."); return
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    safe_bot_username = escape_markdown(BOT_USERNAME, version=2) if BOT_USERNAME else "the bot"
    minutes_display = DELETE_AFTER_SECONDS // 60
    
    text_lines = [
        "✨ *File Portal Updated\\!* ✨", # Bold
        "",
        "Select the content you'd like to receive below\\.",
        f"Files are sent via @{safe_bot_username} and auto\\-delete after {minutes_display} minutes\\."
    ]
    text = "\n".join(text_lines)

    try:
        await bot.send_message(
            chat_id=PUBLIC_CHANNEL_ID, text=text, reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
        )
        logger.info(f"Button message sent/updated in {PUBLIC_CHANNEL_ID}.")
    except Exception as e:
        logger.error(f"Failed to send button message to {PUBLIC_CHANNEL_ID}: {e}", exc_info=True)
        if "parse" in str(e).lower(): logger.error(f"Problematic MarkdownV2 text for buttons was: {text}")


async def get_chat_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    chat_id_val = chat.id if chat else "N/A"
    chat_type_val = chat.type if chat else "N/A"
    user_id_val = user.id if user else "N/A"
    response_text = f"Chat ID: {chat_id_val}\nChat Type: {chat_type_val}"
    if user: response_text += f"\nYour User ID: {user_id_val}"
    logger.info(f"/chatid by user {user_id_val} in chat {chat_id_val} (type: {chat_type_val}).")
    await update.message.reply_text(response_text, parse_mode=None) # Send as plain text


async def post_init_hook(application: Application):
    logger.info("Running post-initialization tasks...")
    if not all([BOT_TOKEN, BOT_USERNAME, PUBLIC_CHANNEL_ID]):
        logger.warning("post_init: Critical configs missing. Functionality impaired.")
    try:
        bot_info = await application.bot.get_me()
        logger.info(f"Bot init: @{bot_info.username} (ID: {bot_info.id})")
        if BOT_USERNAME and BOT_USERNAME != bot_info.username:
             logger.warning(f"MISMATCH: Env BOT_USERNAME ('{BOT_USERNAME}') vs actual ('{bot_info.username}')!")
    except Exception as e: logger.error(f"Failed bot info in post_init: {e}", exc_info=True)

    if AUTO_SETUP_BUTTONS_ON_START:
        if PUBLIC_CHANNEL_ID and BOT_USERNAME:
             logger.info("post_init: Scheduling button setup...")
             application.job_queue.run_once(lambda ctx: setup_buttons(bot=application.bot), when=2)
        else: logger.error("post_init: Cannot auto-setup; config missing for PUBLIC_CHANNEL_ID or BOT_USERNAME.")
    else: logger.info("post_init: Auto button setup disabled.")

# === Main Bot Execution Function ===
def run_telegram_bot_application():
    logger.info("Attempting to start Telegram bot application...")
    if not BOT_TOKEN: logger.critical("CRITICAL: BOT_TOKEN missing."); return

    if not SEASONS: logger.warning("SEASONS empty.")
    elif all(not fid or fid.startswith('FILE_ID_') for sf_list in SEASONS.values() for fid in sf_list if isinstance(sf_list, list)):
         logger.warning("SEASONS only placeholders/empty lists.")

    defaults = Defaults(parse_mode=ParseMode.MARKDOWN_V2) # Default parse mode for bot
    
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
        logger.critical(f"CRITICAL: Failed Telegram app build: {e}", exc_info=True)
        return

    logger.info("--- Bot Configuration Summary ---")
    logger.info(f"Bot Username: @{BOT_USERNAME or 'N/A'}")
    logger.info(f"Public Channel: {PUBLIC_CHANNEL_ID or 'N/A'}")
    logger.info(f"Private Channel (Ref): {PRIVATE_CHANNEL_ID or 'N/A'}")
    logger.info(f"Content Keys: {list(SEASONS.keys())}")
    logger.info(f"Delete After: {DELETE_AFTER_SECONDS}s")
    logger.info(f"Auto Setup Buttons: {AUTO_SETUP_BUTTONS_ON_START}")
    logger.info("--------------------------------")

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("chatid", get_chat_id_handler))
    # No CallbackQueryHandler in this simpler version

    logger.info("Starting Telegram bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Telegram bot polling stopped.")

# === Main Entry Point ===
if __name__ == '__main__':
    logger.info("Script execution starting...")
    if not all([BOT_TOKEN, BOT_USERNAME, PUBLIC_CHANNEL_ID]):
        logger.critical("CRITICAL: Essential env vars (BOT_TOKEN, BOT_USERNAME, PUBLIC_CHANNEL_ID) not all set. Exiting.")
        # import sys; sys.exit(1) # Consider hard exit
    else:
        logger.info("Essential configurations appear loaded.")
        try:
            keep_alive()
            logger.info("Keep_alive server thread initiated.")
        except Exception as e_ka:
            logger.error(f"Could not start keep_alive: {e_ka}", exc_info=True)
        
        try: run_telegram_bot_application()
        except KeyboardInterrupt: logger.info("Bot process stopped by user (Ctrl+C).")
        except Exception as e_main: logger.critical(f"UNHANDLED EXCEPTION in main: {e_main}", exc_info=True)
    logger.info("Script execution finished or bot stopped.")
