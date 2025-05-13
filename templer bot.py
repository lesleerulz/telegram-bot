# ===----------------------------------------------------------------------=== #
#                    Refined Telegram File Share Bot                         #
# ===----------------------------------------------------------------------=== #
#
# Purpose: Shares files (e.g., videos) stored in a private Telegram channel
#          with users via a public channel interface using inline buttons
#          and deep-linking. Automatically cleans up sent files after a delay.
#
# Workflow:
# 1. Admin runs `setup_buttons` (or enables it on startup) to post/update
#    a message with "Season" buttons in the PUBLIC_CHANNEL.
# 2. User clicks a button (e.g., "Season 1").
# 3. Button URL (t.me/templer1bot?start=season1) opens a DM chat with the bot.
# 4. Bot's `start_handler` receives "season1" via deep-link arguments.
# 5. Bot looks up "season1" in the SEASONS config to get the list of file_ids.
# 6. Bot sends each file (using its file_id) to the user in the DM.
# 7. For each sent file message, the bot schedules a job using JobQueue
#    to delete that specific message after DELETE_AFTER_SECONDS.
# 8. The `delete_message_job` function runs when scheduled, deleting the file message.
#
# ===----------------------------------------------------------------------=== #

import os
import logging
import asyncio
from telegram import (
    Update,
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument # Consider using this for sending multiple docs if needed later
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

# === 1. Logging Setup ===
# Configure logging to see bot activity and errors.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # Change to logging.DEBUG for more detailed output
)
# Suppress overly verbose logs from underlying HTTP library
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# === 2. Configuration ===
# Your specific details have been inserted below.
# You MUST still fill in the SEASONS dictionary with your other actual file_ids.

# --- Critical Configuration ---
# BOT_TOKEN: Your bot's unique API key from @BotFather
BOT_TOKEN = os.getenv('BOT_TOKEN', '8085729451:AAEMfsjqZ9TYnYZmbsTROe5WKDBvM-caoRc') # Your Token
# BOT_USERNAME: Your bot's username (WITHOUT the '@'). Needed for deep links.
BOT_USERNAME = os.getenv('BOT_USERNAME', 'templer1bot') # Your Username

# --- Channel Configuration ---
# PRIVATE_CHANNEL_ID: Numeric ID of the private channel where files are stored
PRIVATE_CHANNEL_ID = os.getenv('PRIVATE_CHANNEL_ID', '-1002668516099') # Your Private Channel ID
# PUBLIC_CHANNEL_ID: Username or numeric ID of the public channel for buttons
PUBLIC_CHANNEL_ID = os.getenv('PUBLIC_CHANNEL_ID', '@lesleechannel') # Your Public Channel Username

# --- File & Season Configuration ---
# SEASONS: Dictionary mapping simple keys (used in deep links) to lists of file IDs.
# !!! CRITICAL: REPLACE THE REMAINING PLACEHOLDERS BELOW WITH YOUR REAL FILE IDs !!!
# How to get File IDs:
#   1. Upload files to your PRIVATE channel (-1002668516099).
#   2. Forward *each* file message to @RawDataBot or @JsonDumpBot.
#   3. Find the `file_id` field within the `document` or `video` object.
#   4. Copy the long string (file_id) and paste it below.
# IMPORTANT: Bot must be ADMIN in the PRIVATE channel (-1002668516099) to access files by ID.
SEASONS = {
    # Example: Replace 'FILE_ID_...' with YOUR actual file IDs.
    'season1': [
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
        'BQACAgQAAxkBAAEBFdRoIyhfAWiiAUhdtrryj7NOjFW8pwACCiQAA1AZUfPBIAQINEVLNgQ',#15
        'BQACAgQAAxkBAAEBFdhoIyiVNqJxHKEkceFyPylG5vH0ugACCyQAA1AZUat5zS5woEANNgQ',#16
    ],
    'season2': [
        'FILE_ID_S02E01', # <<<=== REPLACE THIS with the ID for S02E01
        'FILE_ID_S02E02', # <<<=== REPLACE THIS with the ID for S02E02
        # Add more file IDs for Season 2 here...
    ],
    # Add more keys (like 'season3', 'movies', etc.) and their file ID lists as needed
}

# --- Behavior Configuration ---
# Time in seconds after which sent files should be deleted from the user's chat.
DELETE_AFTER_SECONDS = 20 * 60  # 20 minutes (1200 seconds). You can change this value.

# Set this to True if you want the bot to automatically post/update
# the button message in the public channel (@lesleechannel) on startup.
# Requires bot to be ADMIN in @lesleechannel.
# !!! IMPORTANT: SET THIS BACK TO False AFTER BUTTONS ARE POSTED !!!
AUTO_SETUP_BUTTONS_ON_START = True # <<<=== SET TO TRUE TO POST BUTTONS ON NEXT RUN

# === 3. Core Bot Logic ===

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
             if "FILE_ID_INVALID" in str(e) and failed_count == 1:
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
         # Optionally notify user about partial success
         # await context.bot.send_message(chat_id, f"ℹ️ Finished sending files for '{season_key}'. {sent_count} sent successfully, {failed_count} failed.")
    else:
         logger.info(f"Successfully sent all {sent_count} files for '{season_key}' to user {user.id}.")
         # Optionally send a completion message:
         # await context.bot.send_message(chat_id, f"✅ All files for '{season_key}' sent!")


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
        if "Message to delete not found" in str(e) or "MESSAGE_ID_INVALID" in str(e):
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

    if not PUBLIC_CHANNEL_ID or PUBLIC_CHANNEL_ID == '@YourPublicChannelUsername': # Check against default placeholder
        logger.error("PUBLIC_CHANNEL_ID is not configured correctly. Cannot setup buttons.")
        return
    if not BOT_USERNAME or BOT_USERNAME == 'YourBotUsername': # Check against default placeholder
        logger.error("BOT_USERNAME is not configured correctly. Button links will be incorrect.")
        return

    keyboard = []
    if not SEASONS:
        logger.warning("SEASONS dictionary is empty. No buttons to create.")

    # Filter out seasons with no valid file IDs before creating buttons
    valid_seasons = {key: ids for key, ids in SEASONS.items() if any(fid and not fid.startswith('FILE_ID_') for fid in ids)}

    if not valid_seasons:
         logger.warning("No seasons with valid file IDs found. Cannot create buttons.")
         # Optionally send an update message indicating no content available
         # try:
         #    await bot.send_message(chat_id=PUBLIC_CHANNEL_ID, text="No content is currently available.")
         # except Exception as e:
         #    logger.error(f"Failed to send 'no content' message: {e}")
         return # Stop if no valid seasons

    for key in sorted(valid_seasons.keys()): # Sort keys for consistent button order
        # Create button text (e.g., "Season 1", "Movies")
        button_text = f"🎬 {key.replace('season', 'Season ').replace('_', ' ').title()}"
        button_url = f"https://t.me/{BOT_USERNAME}?start={key}"
        keyboard.append([InlineKeyboardButton(button_text, url=button_url)])

    if not keyboard:
         logger.error("Button generation failed unexpectedly even with valid seasons.")
         return

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
         "✨ **Welcome!** ✨\n\n"
         "Select the content you'd like to receive below.\n"
         "Clicking a button will start a chat with me (@" + BOT_USERNAME + "), and I'll send you the files directly.\n\n"
         f"_(Files are automatically removed after {DELETE_AFTER_SECONDS // 60} minutes.)_"
     )

    try:
        # Consider trying to *edit* an existing message first if you know its ID,
        # otherwise send a new one. Sending a new one is simpler.
        await bot.send_message(
            chat_id=PUBLIC_CHANNEL_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        logger.info(f"Successfully sent/updated button message in channel {PUBLIC_CHANNEL_ID}.")
    except Forbidden as e:
        logger.error(f"Failed to send button message to {PUBLIC_CHANNEL_ID}: Forbidden. Check if bot is ADMIN in the channel. {e}")
    except BadRequest as e:
        logger.error(f"Failed to send button message to {PUBLIC_CHANNEL_ID}: BadRequest. Check if PUBLIC_CHANNEL_ID ('{PUBLIC_CHANNEL_ID}') is correct (username or numeric ID). {e}")
    except TelegramError as e:
        logger.error(f"Telegram error sending button message to {PUBLIC_CHANNEL_ID}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error sending button message to {PUBLIC_CHANNEL_ID}: {e}")


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

    # Check if the user is the bot admin (optional, but recommended for sensitive commands)
    # admin_id = 12345678 # Replace with your actual Telegram User ID
    # if user and user.id == admin_id:
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)
    # else:
    #    logger.warning(f"Unauthorized user {user.id} attempted to use /chatid in chat {chat_id}.")
    #    await update.message.reply_text("Sorry, this command is restricted.")


async def post_init_hook(application: Application):
    """Runs tasks after the bot application has been initialized."""
    logger.info("Running post-initialization tasks...")
    try:
        bot_info = await application.bot.get_me()
        actual_bot_username = bot_info.username
        logger.info(f"Bot initialized: @{actual_bot_username} (ID: {bot_info.id})")
        # Verify configured username matches actual bot username
        if BOT_USERNAME != actual_bot_username:
             logger.warning(f"CONFIG MISMATCH: Configured BOT_USERNAME ('{BOT_USERNAME}') does not match actual bot username ('{actual_bot_username}')!")
             # You might want to update BOT_USERNAME dynamically here, but be cautious
             # BOT_USERNAME = actual_bot_username # Uncomment cautiously

    except Exception as e:
         logger.error(f"Failed to get bot info during post_init: {e}")


    if AUTO_SETUP_BUTTONS_ON_START:
        if not PUBLIC_CHANNEL_ID or PUBLIC_CHANNEL_ID == '@YourPublicChannelUsername' or not BOT_USERNAME or BOT_USERNAME == 'YourBotUsername':
             logger.error("Cannot auto-setup buttons: PUBLIC_CHANNEL_ID or BOT_USERNAME is missing/incorrect in config.")
        else:
             logger.info("Attempting to set up buttons in public channel on startup...")
             # Schedule the task to run shortly after startup
             application.job_queue.run_once(lambda ctx: setup_buttons(bot=application.bot), when=2) # Run after 2 seconds
    else:
        logger.info("Automatic button setup on startup is disabled (AUTO_SETUP_BUTTONS_ON_START=False).")
        logger.info("Use the /setupbuttons command (if enabled) or run setup_buttons function manually if needed.")


# === 4. Main Execution ===

def main() -> None:
    """Sets up the application and runs the bot."""

    # --- Pre-run Checks ---
    # Token and Username are checked implicitly by trying to build the application
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
            .job_queue(JobQueue())
            .post_init(post_init_hook)
            .build()
        )
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to build application. Check BOT_TOKEN. Error: {e}")
        return # Exit if application can't be built

    # --- Log Configuration Summary AFTER basic build ---
    logger.info("--- Bot Configuration Summary ---")
    logger.info(f"Bot Username (Configured): @{BOT_USERNAME}") # Actual username logged in post_init
    logger.info(f"Public Channel: {PUBLIC_CHANNEL_ID}")
    logger.info(f"Private Channel ID (Reference): {PRIVATE_CHANNEL_ID}")
    logger.info(f"Defined Season Keys: {list(SEASONS.keys())}")
    logger.info(f"Auto-delete files after: {DELETE_AFTER_SECONDS} seconds")
    logger.info(f"Auto-setup buttons on start: {AUTO_SETUP_BUTTONS_ON_START}")
    logger.info("--------------------------------")


    # --- Register Handlers ---
    application.add_handler(CommandHandler("start", start_handler))

    # Optional: Command to manually trigger button setup (e.g., run by admin)
    # Needs careful permission checking if you enable it widely.
    # async def restricted_setup_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     user_id = update.effective_user.id
    #     ADMIN_USER_ID = 12345678 # Replace with YOUR Telegram User ID
    #     if user_id == ADMIN_USER_ID:
    #         logger.info(f"Admin user {user_id} triggered /setupbuttons")
    #         await setup_buttons(context=context)
    #     else:
    #         logger.warning(f"Unauthorized user {user_id} tried to run /setupbuttons")
    #         await update.message.reply_text("You are not authorized to use this command.")
    # application.add_handler(CommandHandler("setupbuttons", restricted_setup_buttons))

    # Command to get chat ID (useful for finding PRIVATE_CHANNEL_ID)
    application.add_handler(CommandHandler("chatid", get_chat_id_handler)) # Keep restricted version if needed


    # --- Start Bot ---
    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES) # Process all update types

    logger.info("Bot polling stopped.")


if __name__ == '__main__':
    main()


# === 5. Final Setup Checklist ===
# -------------------------------------------------------------------------------
# ✔️  **Configuration Set**: Your Token, Username, Channel IDs are pre-filled above.
# ✔️  **Populate `SEASONS`**: **YOU MUST DO THIS!** Replace the remaining `'FILE_ID_...'` placeholders in the `SEASONS` dictionary with your actual file IDs obtained using `@RawDataBot` or `@JsonDumpBot`.
# ✔️  **Admin Permissions**: Ensure your bot (@templer1bot) is an ADMIN in:
#      - The **Private Channel** (`-1002668516099`) (to access files).
#      - The **Public Channel** (`@lesleechannel`) (to post messages).
# ✔️  **`AUTO_SETUP_BUTTONS_ON_START`**: Currently `True`. Run the bot once to post buttons. Then STOP the bot, change this back to `False`, SAVE, and restart the bot for normal operation.
# ✔️  **Install Library**: Open terminal/PyCharm terminal: `pip install "python-telegram-bot[job-queue]"` (You already did this).
# ✔️  **Run**: Save this code as a `.py` file (e.g., `templer_bot.py`) and run from terminal/PyCharm: `python templer_bot.py`
# -------------------------------------------------------------------------------
