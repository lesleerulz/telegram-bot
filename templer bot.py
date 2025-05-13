# ===----------------------------------------------------------------------=== #
#                    Refined Telegram File Share Bot                         #
# ===----------------------------------------------------------------------=== #
# ... (your existing comments at the top) ...
# ===----------------------------------------------------------------------=== #

# 1. KEEP ALIVE IMPORT (Add this at the top)
from keep_alive import keep_alive

# 2. STANDARD IMPORTS (Your existing imports)
import os
import logging
import asyncio
# import threading # Not strictly needed here if keep_alive.py handles its own thread
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

# === 1. Logging Setup === (Your existing logging setup)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
# Suppress Flask's default development server logs if too noisy, or let them be for debugging
logging.getLogger("werkzeug").setLevel(logging.WARNING) # Add this for Flask's server
logger = logging.getLogger(__name__)

# === 2. Configuration === (Your existing configuration)
# ... (BOT_TOKEN, BOT_USERNAME, PRIVATE_CHANNEL_ID, PUBLIC_CHANNEL_ID, SEASONS, DELETE_AFTER_SECONDS, AUTO_SETUP_BUTTONS_ON_START) ...
# (Make sure the missing comma in SEASONS['season1'] is fixed here too!)
# Corrected SEASONS (example part):
SEASONS = {
    'season1': [
        # ... all your file IDs ...
        'BQACAgQAAxkBAAEBFdRoIyhfAWiiAUhdtrryj7NOjFW8pwACCiQAA1AZUfPBIAQINEVLNgQ', #15 <-- Comma added
        'BQACAgQAAxkBAAEBFdhoIyiVNqJxHKEkceFyPylG5vH0ugACCyQAA1AZUat5zS5woEANNgQ', #16
    ],
    'season2': [
        'FILE_ID_S02E01',
        'FILE_ID_S02E02',
    ],
}
# BOT_TOKEN, BOT_USERNAME, etc. definitions remain the same as your provided script.
# BOT_TOKEN = os.getenv('BOT_TOKEN', '8085729451:AAEMfsjqZ9TYnYZmbsTROe5WKDBvM-caoRc')
# BOT_USERNAME = os.getenv('BOT_USERNAME', 'templer1bot')
# PRIVATE_CHANNEL_ID = os.getenv('PRIVATE_CHANNEL_ID', '-1002668516099')
# PUBLIC_CHANNEL_ID = os.getenv('PUBLIC_CHANNEL_ID', '@lesleechannel')
# DELETE_AFTER_SECONDS = 20 * 60
# AUTO_SETUP_BUTTONS_ON_START = True


# === 3. Core Bot Logic === (All your async functions: start_handler, delete_message_job, etc. - NO CHANGES NEEDED INSIDE THESE FUNCTIONS)
# ... async def start_handler(...): ...
# ... async def delete_message_job(...): ...
# ... async def setup_buttons(...): ...
# ... async def get_chat_id_handler(...): ...
# ... async def post_init_hook(...): ...
# (Just paste all those functions here as they were)

# COPY ALL YOUR FUNCTION DEFINITIONS HERE:
# start_handler, delete_message_job, setup_buttons, get_chat_id_handler, post_init_hook
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command, primarily processing deep links."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    args = context.args

    logger.info(f"Received /start command from user {user.id} ({user.username}) in chat {chat_id} with args: {args}")

    if not args:
        # User sent /start manually without deep-link args
        await update.message.reply_text(
            "Hello! 👋 Please use the buttons in our public channel "
            f"({PUBLIC_CHANNEL_ID}) to request files."
        )
        logger.info(f"Sent welcome message to user {user.id} (no deep link args).")
        return

    # Process deep link: first argument is the season key
    season_key = args[0].lower()

    if season_key not in SEASONS:
        await update.message.reply_text(
            "😕 Sorry, I don't recognize that request key. "
            "Please ensure you clicked a valid button from the channel."
        )
        logger.warning(f"User {user.id} requested unknown key: '{season_key}'.")
        return

    file_ids = SEASONS[season_key]

    # Check if the list is empty or only contains placeholder/invalid IDs
    valid_file_ids = [fid for fid in file_ids if fid and not fid.startswith('FILE_ID_')]

    if not valid_file_ids:
        await update.message.reply_text(
            f"🚧 The files for '{season_key}' seem to be missing or not configured correctly yet. "
            "Please check back later or contact an admin."
        )
        logger.warning(f"No valid file IDs found for key '{season_key}' requested by user {user.id}.")
        return

    # Inform the user
    await update.message.reply_text(
        f"✅ Got it! Sending you {len(valid_file_ids)} file(s) for '{season_key}'.\n\n"
        f"🕒 _These files will be automatically deleted in {DELETE_AFTER_SECONDS // 60} minutes._",
        parse_mode=ParseMode.MARKDOWN
    )
    logger.info(f"Processing request for '{season_key}' ({len(valid_file_ids)} files) for user {user.id}.")

    # Send files and schedule deletion
    sent_count = 0
    failed_count = 0
    for index, file_id in enumerate(valid_file_ids):
        try:
            # Using send_document is generally robust for most file types including videos.
            caption = f"{season_key.replace('season', 'Season ').capitalize()} - Part {index + 1}"

            sent_message = await context.bot.send_document(
                chat_id=chat_id,
                document=file_id,
                caption=caption,
                # disable_notification=True # Consider uncommenting if sending many files at once
            )
            sent_count += 1
            logger.info(f"Successfully sent file {index + 1}/{len(valid_file_ids)} (ID: ...{file_id[-10:]}) for '{season_key}' to user {user.id}.")

            # Schedule deletion
            context.job_queue.run_once(
                delete_message_job,
                when=DELETE_AFTER_SECONDS,
                data={'chat_id': chat_id, 'message_id': sent_message.message_id},
                name=f'delete_{chat_id}_{sent_message.message_id}' # Unique job name
            )
            logger.info(f"Scheduled message {sent_message.message_id} for deletion in {DELETE_AFTER_SECONDS}s.")

        except Forbidden as e:
            failed_count += 1
            logger.error(f"Forbidden error sending file {index + 1} (ID: ...{file_id[-10:]}) for '{season_key}' to user {user.id}: {e}. Bot might be blocked or lack permissions.")
            if failed_count == 1: # Notify user only on the first failure of this type
                 await context.bot.send_message(chat_id, "⚠️ I couldn't send one or more files. I might be blocked or lack permissions.")
        except BadRequest as e:
             failed_count += 1
             logger.error(f"BadRequest error sending file {index + 1} (ID: ...{file_id[-10:]}) for '{season_key}' to user {user.id}: {e}. File ID might be invalid or inaccessible.")
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

        # Optional: Add a small delay between sending files if needed
        # await asyncio.sleep(0.5) # e.g., 0.5 second delay

    # Send a summary message if needed
    if failed_count > 0:
         logger.warning(f"Finished sending for '{season_key}' to user {user.id}. Sent: {sent_count}, Failed: {failed_count}.")
    else:
         logger.info(f"Successfully sent all {sent_count} files for '{season_key}' to user {user.id}.")


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    """Job callback function to delete a message."""
    job = context.job
    chat_id = job.data['chat_id']
    message_id = job.data['message_id']

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully auto-deleted message {message_id} from chat {chat_id}.")
    except Forbidden as e:
        logger.warning(f"Could not auto-delete message {message_id} in chat {chat_id}: Forbidden. Bot might lack permissions or be blocked. {e}")
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
    """Creates or updates the message with season buttons in the public channel."""
    if not bot and context:
        bot = context.bot
    elif not bot:
        logger.error("setup_buttons called without a bot instance.")
        return

    # Use os.getenv for checks here as well, in case .env wasn't used or variables were not set
    public_channel_id_val = os.getenv('PUBLIC_CHANNEL_ID', '@YourPublicChannelUsername')
    bot_username_val = os.getenv('BOT_USERNAME', 'YourBotUsername')


    if not public_channel_id_val or public_channel_id_val == '@YourPublicChannelUsername':
        logger.error("PUBLIC_CHANNEL_ID is not configured correctly. Cannot setup buttons.")
        return
    if not bot_username_val or bot_username_val == 'YourBotUsername':
        logger.error("BOT_USERNAME is not configured correctly. Button links will be incorrect.")
        return

    keyboard = []
    if not SEASONS:
        logger.warning("SEASONS dictionary is empty. No buttons to create.")
        # Return if SEASONS is empty
        return


    # Filter out seasons with no valid file IDs before creating buttons
    valid_seasons = {key: ids for key, ids in SEASONS.items() if any(fid and not fid.startswith('FILE_ID_') for fid in ids)}

    if not valid_seasons:
         logger.warning("No seasons with valid file IDs found. Cannot create buttons.")
         return # Stop if no valid seasons

    for key in sorted(valid_seasons.keys()): # Sort keys for consistent button order
        # Create button text (e.g., "Season 1", "Movies")
        button_text = f"🎬 {key.replace('season', 'Season ').replace('_', ' ').title()}"
        button_url = f"https://t.me/{bot_username_val}?start={key}" # Use loaded value
        keyboard.append([InlineKeyboardButton(button_text, url=button_url)])

    if not keyboard: # Should ideally not happen if valid_seasons is populated
         logger.error("Button generation failed unexpectedly even with valid seasons.")
         return

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
         "✨ **Welcome!** ✨\n\n"
         "Select the content you'd like to receive below.\n"
         f"Clicking a button will start a chat with me (@{bot_username_val}), and I'll send you the files directly.\n\n"
         f"_(Files are automatically removed after {DELETE_AFTER_SECONDS // 60} minutes.)_"
     )

    try:
        await bot.send_message(
            chat_id=public_channel_id_val, # Use loaded value
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        logger.info(f"Successfully sent/updated button message in channel {public_channel_id_val}.")
    except Forbidden as e:
        logger.error(f"Failed to send button message to {public_channel_id_val}: Forbidden. Check if bot is ADMIN in the channel. {e}")
    except BadRequest as e:
        logger.error(f"Failed to send button message to {public_channel_id_val}: BadRequest. Check if PUBLIC_CHANNEL_ID ('{public_channel_id_val}') is correct. {e}")
    except TelegramError as e:
        logger.error(f"Telegram error sending button message to {public_channel_id_val}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error sending button message to {public_channel_id_val}: {e}")


async def get_chat_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with the current chat's ID. Useful for finding PRIVATE_CHANNEL_ID."""
    chat = update.effective_chat
    user = update.effective_user
    chat_id = chat.id
    response_text = f"Chat ID: `{chat_id}`\nChat Type: {chat.type}"
    if user:
        logger.info(f"/chatid command executed by user {user.id} in chat {chat_id} ({chat.type}).")
    else:
         logger.info(f"/chatid command executed in chat {chat_id} ({chat.type}).")
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)


async def post_init_hook(application: Application):
    """Runs tasks after the bot application has been initialized."""
    logger.info("Running post-initialization tasks...")

    # Get effective values that the application is using for bot_username
    # This bot_username would be from os.getenv at the top of the script
    current_bot_username_config = BOT_USERNAME
    current_public_channel_config = PUBLIC_CHANNEL_ID

    try:
        bot_info = await application.bot.get_me()
        actual_bot_username = bot_info.username
        logger.info(f"Bot initialized: @{actual_bot_username} (ID: {bot_info.id})")
        if current_bot_username_config and current_bot_username_config != actual_bot_username:
             logger.warning(f"CONFIG MISMATCH: Configured BOT_USERNAME ('{current_bot_username_config}') does not match actual bot username ('{actual_bot_username}')!")

    except Exception as e:
         logger.error(f"Failed to get bot info during post_init: {e}")


    if AUTO_SETUP_BUTTONS_ON_START:
        if not current_public_channel_config or current_public_channel_config == '@YourPublicChannelUsername' or \
           not current_bot_username_config or current_bot_username_config == 'YourBotUsername':
             logger.error("Cannot auto-setup buttons: PUBLIC_CHANNEL_ID or BOT_USERNAME is missing/incorrect in config (checked in post_init).")
        else:
             logger.info("Attempting to set up buttons in public channel on startup (via post_init_hook)...")
             application.job_queue.run_once(lambda ctx: setup_buttons(bot=application.bot), when=2)
    else:
        logger.info("Automatic button setup on startup is disabled (AUTO_SETUP_BUTTONS_ON_START=False).")


# === 4. Main Bot Execution Function (this used to be main()) ===
def run_telegram_bot():
    """Sets up the application and runs the bot."""
    logger.info("Attempting to start Telegram bot application...")

    # --- Pre-run Checks ---
    # BOT_TOKEN is critical. If not found by os.getenv (and no fallback), ApplicationBuilder will fail.
    # Let's add an explicit check here for clarity, though ApplicationBuilder will also raise an error.
    if not BOT_TOKEN:
        logger.critical("CRITICAL: BOT_TOKEN is not set. Cannot start bot. Check environment variables.")
        return

    if not SEASONS:
        logger.warning("WARNING: SEASONS dictionary is empty. Bot will run but cannot serve any files until populated.")
    elif all(not fid or fid.startswith('FILE_ID_') for season_files in SEASONS.values() for fid in season_files):
         logger.warning("WARNING: SEASONS dictionary only contains placeholders or is empty. Bot cannot serve files.")

    # --- Application Setup ---
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)
    try:
        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .defaults(defaults)
            .job_queue(JobQueue()) # This is the line that requires [job-queue] extras
            .post_init(post_init_hook)
            .build()
        )
    except Exception as e: # Catch-all for build failures, including the JobQueue one or missing token
        logger.critical(f"CRITICAL: Failed to build Telegram application. Check BOT_TOKEN and package installations (esp. for JobQueue). Error: {e}", exc_info=True)
        return

    # --- Log Configuration Summary AFTER basic build ---
    logger.info("--- Bot Configuration Summary ---")
    logger.info(f"Bot Username (Configured): @{BOT_USERNAME}")
    logger.info(f"Public Channel: {PUBLIC_CHANNEL_ID}")
    logger.info(f"Private Channel ID (Reference): {PRIVATE_CHANNEL_ID}")
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


# === 5. Main Entry Point (if __name__ == '__main__') ===
if __name__ == '__main__':
    logger.info("Script starting...")

    # Start the keep_alive Flask server (from keep_alive.py)
    # This assumes keep_alive() starts the Flask server in a separate, non-blocking thread.
    try:
        keep_alive()
        logger.info("Keep_alive server thread initiated.")
    except Exception as e_ka:
        logger.error(f"Error starting keep_alive server: {e_ka}", exc_info=True)
        # Depending on how critical keep_alive is, you might want to exit here
        # For now, we'll log the error and try to run the bot anyway.

    # Run the main Telegram bot logic
    try:
        run_telegram_bot()
    except KeyboardInterrupt:
        logger.info("Bot process interrupted by user (KeyboardInterrupt).")
    except Exception as e_main_bot:
        # This catches any unexpected error during the bot's main run that wasn't caught by run_telegram_bot() itself
        logger.critical(f"An unhandled error occurred in the main bot execution block: {e_main_bot}", exc_info=True)
    finally:
        logger.info("Script execution finished or bot has stopped.")

# === 6. Final Setup Checklist === (Your existing checklist - no changes needed here)
# ...
