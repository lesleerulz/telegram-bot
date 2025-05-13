# ===----------------------------------------------------------------------=== #
#                    Refined Telegram File Share Bot                         #
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
# import threading # Not strictly needed here if keep_alive.py handles its own thread correctly
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

# === Logging Setup ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING) # For Flask's server
logger = logging.getLogger(__name__)

# === Configuration ===
# These MUST be set as environment variables on your hosting platform (e.g., Render)
# or in a .env file for local testing (which load_dotenv() handles).
BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME')
PRIVATE_CHANNEL_ID = os.getenv('PRIVATE_CHANNEL_ID') # For reference
PUBLIC_CHANNEL_ID = os.getenv('PUBLIC_CHANNEL_ID')

# Check if critical configurations are loaded
if not BOT_TOKEN:
    logger.critical("CRITICAL ERROR: BOT_TOKEN is not set in the environment. Please set it on your hosting platform or in .env file.")
    # Optionally, you could raise an error or exit here, but main() will also check.
if not BOT_USERNAME:
    logger.warning("WARNING: BOT_USERNAME is not set. Deep links for buttons might be incorrect.")
if not PUBLIC_CHANNEL_ID:
    logger.warning("WARNING: PUBLIC_CHANNEL_ID is not set. Bot may not be able to post buttons.")


# --- File & Season Configuration ---
SEASONS = {
    'apothecary diaries ss1 dual 1080p': [
        'BQACAgQAAxkBAAEBEWhoImGp0GLWjLBTaJ90ZcIYtdFtvQACtSMAA1AZUQABXCxSF360SzYE', #1
        'BQACAgQAAxkBAAEBEX9oInhdz1T_S7sJEifWD91VL5vO7QACzyMAA1AZUZ107KoTZlUXNgQ', #2
        'BQACAgQAAxkBAAEBFY5oIyNYobHZHWWk2DJ2Hjkx99LgRAAC1CMAA1AZUdl6cVfp1NJENgQ',#3
        'BQACAgQAAxkBAAEBFZRoIyPO_rPhGaOyzbrB9C1i0kVQFAAC2CMAA1AZUdTTQh9FDanpNgQ',#4
        'BQACAgQAAxkBAAEBFZ5oIyRnTpQuMZmUL6G0WhoO5B4aTAAC7CMAA1AZUbD3Pqh5iI1gNgQ',#5
        'BQACAgQAAxkBAAEBFaRoIyUvMwXAz9PJcwM1IppLokbTxwAC_iMAA1AZUa4d5x39FGS6NgQ',#6
        'BQACAgQAAxkBAAEBFapoIyWcR6Le331xB_Hy3e3yyLuNlwAC_yMAA1AZUSGVkYFzvP5GNgQ',#7
        'BQACAgQAAxkBAAEBFa5oIyXqcbLkpRD8H0JIea1iQcBN9QACASQAA1AZUQIF8Id9ze3tNgQ',#8
        'BQACAgQAAxkBAAEBFbBoIyYNu-Oz0H_CmwSiouSiq2WESAACAyQAA1AZUZlu2B38psTBNgQ',#9
        'BQACAgQAAxkBAAEBFbJoIyY5Y0wmYpBtM6pl9f4HNN6XzwACBSQAA1AZUeb9OVa0RYU1NgQ',#10
        'BQACAgQAAxkBAAEBFbdoIyaq6xhaL0IQieSe4wakJd5WiQACBiQAA1AZUbUJS4dMKZIKNgQ',#11
        'BQACAgQAAxkBAAEBFbloIybcbew4-C-ALKSiyYbX0LvZzQACByQAA1AZUcm08Upui6CaNgQ',#12
        'BQACAgQAAxkBAAEBFcxoIyfdR-Q4uWTvvCYYJRK1vX129AACCCQAA1AZUUUV06vwTECfNgQ',#13
        'BQACAgQAAxkBAAEBFcxoIyfdR-Q4uWTvvCYYJRK1vX129AACCCQAA1AZUUUV06vwTECfNgQ',#14
        'BQACAgQAAxkBAAEBFdRoIyhfAWiiAUhdtrryj7NOjFW8pwACCiQAA1AZUfPBIAQINEVLNgQ', #15
        'BQACAgQAAxkBAAEBFdhoIyiVNqJxHKEkceFyPylG5vH0ugACCyQAA1AZUat5zS5woEANNgQ', #16
    ],
    'season2': [
        'FILE_ID_S02E01',
        'FILE_ID_S02E02',
    ],
}

# --- Behavior Configuration ---
DELETE_AFTER_SECONDS = 20 * 60
AUTO_SETUP_BUTTONS_ON_START = True # Set to True for initial run to post buttons

# === Core Bot Logic ===

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command, primarily processing deep links."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    args = context.args

    # Crucial: Check if PUBLIC_CHANNEL_ID is loaded, as it's used in the no-args response
    if not PUBLIC_CHANNEL_ID:
        logger.error("start_handler: PUBLIC_CHANNEL_ID is not configured. Cannot provide channel link.")
        # Potentially send a more generic message or just log and return
        if update.message: # Check if update.message exists
            await update.message.reply_text("Bot configuration error. Please contact admin.")
        return

    logger.info(f"Received /start command from user {user.id} ({user.username or 'UnknownUser'}) in chat {chat_id} with args: {args}")


    if not args:
        await update.message.reply_text(
            f"Hello! 👋 Please use the buttons in our public channel ({PUBLIC_CHANNEL_ID}) to request files."
        )
        logger.info(f"Sent welcome message to user {user.id} (no deep link args).")
        return

    season_key = args[0].lower()

    if season_key not in SEASONS:
        await update.message.reply_text(
            "😕 Sorry, I don't recognize that request key. "
            "Please ensure you clicked a valid button from the channel."
        )
        logger.warning(f"User {user.id} requested unknown key: '{season_key}'.")
        return

    file_ids = SEASONS.get(season_key, [])
    valid_file_ids = [fid for fid in file_ids if fid and not fid.startswith('FILE_ID_')]

    if not valid_file_ids:
        await update.message.reply_text(
            f"🚧 The files for '{season_key}' seem to be missing or not configured correctly yet. "
            "Please check back later or contact an admin."
        )
        logger.warning(f"No valid file IDs found for key '{season_key}' requested by user {user.id}.")
        return

    await update.message.reply_text(
        f"✅ Got it! Sending you {len(valid_file_ids)} file(s) for '{season_key}'.\n\n"
        f"🕒 _These files will be automatically deleted in {DELETE_AFTER_SECONDS // 60} minutes._",
        parse_mode=ParseMode.MARKDOWN
    )
    logger.info(f"Processing request for '{season_key}' ({len(valid_file_ids)} files) for user {user.id}.")

    sent_count = 0
    failed_count = 0
    for index, file_id in enumerate(valid_file_ids):
        try:
            caption = f"{season_key.replace('season', 'Season ').capitalize()} - Part {index + 1}"
            sent_message = await context.bot.send_document(
                chat_id=chat_id,
                document=file_id,
                caption=caption,
            )
            sent_count += 1
            logger.info(f"Successfully sent file {index + 1}/{len(valid_file_ids)} (ID: ...{file_id[-10:]}) for '{season_key}' to user {user.id}.")

            context.job_queue.run_once(
                delete_message_job,
                when=DELETE_AFTER_SECONDS,
                data={'chat_id': chat_id, 'message_id': sent_message.message_id},
                name=f'delete_{chat_id}_{sent_message.message_id}'
            )
            logger.info(f"Scheduled message {sent_message.message_id} for deletion in {DELETE_AFTER_SECONDS}s.")

        except Forbidden as e:
            failed_count += 1
            logger.error(f"Forbidden error sending file {index + 1} (ID: ...{file_id[-10:]}) for '{season_key}' to user {user.id}: {e}.")
            if failed_count == 1:
                 await context.bot.send_message(chat_id, "⚠️ I couldn't send one or more files. I might be blocked or lack permissions.")
        except BadRequest as e:
             failed_count += 1
             logger.error(f"BadRequest error sending file {index + 1} (ID: ...{file_id[-10:]}) for '{season_key}' to user {user.id}: {e}.")
             if "FILE_ID_INVALID" in str(e).upper() and failed_count == 1:
                 await context.bot.send_message(chat_id, f"⚠️ Couldn't send file {index + 1}. The file ID seems invalid or the file was removed.")
             elif failed_count == 1:
                 await context.bot.send_message(chat_id, f"⚠️ Couldn't send file {index + 1} due to a request error.")
        except TelegramError as e:
            failed_count += 1
            logger.error(f"Telegram error sending file {index + 1} (ID: ...{file_id[-10:]}) for '{season_key}' to user {user.id}: {e}")
            if failed_count == 1:
                 await context.bot.send_message(chat_id, f"⚠️ An error occurred while sending file {index + 1}. Please try again later.")
        except Exception as e:
            failed_count += 1
            logger.exception(f"Unexpected error sending file {index + 1} (ID: ...{file_id[-10:]}) for '{season_key}' to user {user.id}: {e}")
            if failed_count == 1:
                 await context.bot.send_message(chat_id, f"⚠️ An unexpected error occurred sending file {index + 1}.")

    if failed_count > 0:
         logger.warning(f"Finished sending for '{season_key}' to user {user.id}. Sent: {sent_count}, Failed: {failed_count}.")
    else:
         logger.info(f"Successfully sent all {sent_count} files for '{season_key}' to user {user.id}.")


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data['chat_id']
    message_id = job.data['message_id']
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully auto-deleted message {message_id} from chat {chat_id}.")
    except Forbidden as e:
        logger.warning(f"Could not auto-delete message {message_id} in chat {chat_id}: Forbidden. {e}")
    except BadRequest as e:
        if "Message to delete not found" in str(e) or "MESSAGE_ID_INVALID" in str(e).upper():
            logger.info(f"Message {message_id} in chat {chat_id} already deleted.")
        else:
            logger.warning(f"Could not auto-delete message {message_id} in chat {chat_id}: BadRequest. {e}")
    except TelegramError as e:
        logger.error(f"Telegram error during auto-deletion of message {message_id} in chat {chat_id}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during auto-deletion of message {message_id} in chat {chat_id}: {e}")


async def setup_buttons(context: ContextTypes.DEFAULT_TYPE = None, bot: Bot = None):
    if not bot and context:
        bot = context.bot
    elif not bot:
        logger.error("setup_buttons called without a bot instance.")
        return

    if not PUBLIC_CHANNEL_ID or not BOT_USERNAME:
        logger.error("Cannot setup buttons: PUBLIC_CHANNEL_ID or BOT_USERNAME is not configured. Check environment variables.")
        return

    keyboard = []
    if not SEASONS:
        logger.warning("SEASONS dictionary is empty. No buttons to create.")
        return

    valid_seasons = {key: ids for key, ids in SEASONS.items() if any(fid and not fid.startswith('FILE_ID_') for fid in ids)}

    if not valid_seasons:
         logger.warning("No seasons with valid file IDs found. Cannot create buttons.")
         return

    for key in sorted(valid_seasons.keys()):
        button_text = f"🎬 {key.replace('season', 'Season ').replace('_', ' ').title()}"
        button_url = f"https://t.me/{BOT_USERNAME}?start={key}"
        keyboard.append([InlineKeyboardButton(button_text, url=button_url)])

    if not keyboard:
         logger.error("Button generation failed unexpectedly.")
         return

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
         "✨ **Welcome!** ✨\n\n"
         "Select the content you'd like to receive below.\n"
         f"Clicking a button will start a chat with me (@{BOT_USERNAME}), and I'll send you the files directly.\n\n"
         f"_(Files are automatically removed after {DELETE_AFTER_SECONDS // 60} minutes.)_"
     )
    try:
        await bot.send_message(
            chat_id=PUBLIC_CHANNEL_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        logger.info(f"Successfully sent/updated button message in channel {PUBLIC_CHANNEL_ID}.")
    except Forbidden as e:
        logger.error(f"Failed to send button message to {PUBLIC_CHANNEL_ID}: Forbidden. Check bot admin rights. {e}")
    except BadRequest as e:
        logger.error(f"Failed to send button message to {PUBLIC_CHANNEL_ID}: BadRequest. Check PUBLIC_CHANNEL_ID. {e}")
    except TelegramError as e:
        logger.error(f"Telegram error sending button message to {PUBLIC_CHANNEL_ID}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error sending button message to {PUBLIC_CHANNEL_ID}: {e}")


async def get_chat_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    chat_id = chat.id
    response_text = f"Chat ID: `{chat_id}`\nChat Type: {chat.type}"
    if user:
        logger.info(f"/chatid command executed by user {user.id} ({user.username or 'UnknownUser'}) in chat {chat_id} ({chat.type}).")
    else:
         logger.info(f"/chatid command executed in chat {chat_id} ({chat.type}).")
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)


async def post_init_hook(application: Application):
    logger.info("Running post-initialization tasks...")

    if not BOT_USERNAME or not PUBLIC_CHANNEL_ID: # Check again before use
         logger.warning("post_init_hook: BOT_USERNAME or PUBLIC_CHANNEL_ID is missing. Button setup might fail or links be incorrect.")
         # Bot will still run, but button setup might not work as expected.

    try:
        bot_info = await application.bot.get_me()
        actual_bot_username = bot_info.username
        logger.info(f"Bot initialized: @{actual_bot_username} (ID: {bot_info.id})")
        if BOT_USERNAME and BOT_USERNAME != actual_bot_username:
             logger.warning(
                 f"CONFIG MISMATCH: Configured BOT_USERNAME ('{BOT_USERNAME}') "
                 f"does not match actual bot username ('{actual_bot_username}')!"
             )
    except Exception as e:
         logger.error(f"Failed to get bot info during post_init: {e}")

    if AUTO_SETUP_BUTTONS_ON_START:
        if not PUBLIC_CHANNEL_ID or not BOT_USERNAME: # Critical check
             logger.error("Cannot auto-setup buttons: PUBLIC_CHANNEL_ID or BOT_USERNAME is missing/incorrect (checked in post_init).")
        else:
             logger.info("Attempting to set up buttons in public channel on startup (via post_init_hook)...")
             application.job_queue.run_once(lambda ctx: setup_buttons(bot=application.bot), when=2)
    else:
        logger.info("Automatic button setup on startup is disabled (AUTO_SETUP_BUTTONS_ON_START=False).")


# === Main Bot Execution Function ===
def run_telegram_bot():
    """Sets up the Telegram application and runs the bot."""
    logger.info("Attempting to start Telegram bot application...")

    # --- Pre-run Critical Check ---
    if not BOT_TOKEN:
        logger.critical("CRITICAL ERROR: BOT_TOKEN is not set. Telegram bot cannot start. Check environment variables.")
        return # Exit this function if token is missing

    # --- Other Pre-run Info/Warnings ---
    if not SEASONS:
        logger.warning("WARNING: SEASONS dictionary is empty. Bot will run but cannot serve any files.")
    elif all(not fid or fid.startswith('FILE_ID_') for season_files in SEASONS.values() for fid in season_files):
         logger.warning("WARNING: SEASONS dictionary only contains placeholders or is empty. Bot cannot serve files.")

    # --- Application Setup ---
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)
    try:
        application = (
            Application.builder()
            .token(BOT_TOKEN) # BOT_TOKEN is now guaranteed to be non-None if we reach here
            .defaults(defaults)
            .job_queue(JobQueue()) # This line requires the [job-queue] extras
            .post_init(post_init_hook)
            .build()
        )
    except ValueError as e:
        # This might catch other ValueErrors, but token is the most common from builder()
        logger.critical(f"CRITICAL: Failed to build Telegram application due to ValueError (likely token issue if not caught above). Error: {e}", exc_info=True)
        return
    except Exception as e:
        # This will catch the "To use `JobQueue`, PTB must be installed via..." error if it's an installation issue
        logger.critical(f"CRITICAL: Failed to build Telegram application. Check package installations (esp. for JobQueue). Error: {e}", exc_info=True)
        return

    # --- Log Configuration Summary AFTER successful build ---
    logger.info("--- Bot Configuration Summary ---")
    logger.info(f"Bot Username (from env): @{BOT_USERNAME or 'NOT SET'}") # Display if set
    logger.info(f"Public Channel (from env): {PUBLIC_CHANNEL_ID or 'NOT SET'}")
    logger.info(f"Private Channel ID (from env, for reference): {PRIVATE_CHANNEL_ID or 'NOT SET'}")
    logger.info(f"Defined Season Keys: {list(SEASONS.keys())}")
    logger.info(f"Auto-delete files after: {DELETE_AFTER_SECONDS} seconds")
    logger.info(f"Auto-setup buttons on start: {AUTO_SETUP_BUTTONS_ON_START}")
    logger.info("--------------------------------")

    # --- Register Handlers ---
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("chatid", get_chat_id_handler))

    # --- Start Bot ---
    logger.info("Starting Telegram bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES) # This is a blocking call

    logger.info("Telegram bot polling stopped.")


# === Main Entry Point ===
if __name__ == '__main__':
    logger.info("Script starting...")

    # 1. Start the Keep-Alive Web Server (Flask app)
    try:
        keep_alive() # Assumes keep_alive() starts Flask in a non-blocking thread
        logger.info("Keep_alive server thread initiated.")
    except Exception as e_ka:
        logger.error(f"Error starting keep_alive server: {e_ka}", exc_info=True)
        # If keep_alive is critical for platform uptime, you might choose to exit or handle differently.
        # For now, we log and continue to try starting the bot.

    # 2. Run the main Telegram bot logic
    # Only proceed if BOT_TOKEN was successfully loaded at the script's global scope
    if BOT_TOKEN:
        try:
            run_telegram_bot()
        except KeyboardInterrupt:
            logger.info("Bot process interrupted by user (KeyboardInterrupt).")
        except Exception as e_main_bot:
            logger.critical(f"An unhandled error occurred in the main bot execution block: {e_main_bot}", exc_info=True)
    else:
        # This case should ideally be caught by the BOT_TOKEN check at the start of run_telegram_bot()
        # or the global scope check, but as a final safeguard.
        logger.critical("CRITICAL ERROR: BOT_TOKEN was not available. Telegram bot did not start.")

    logger.info("Script execution finished or bot has stopped.")
