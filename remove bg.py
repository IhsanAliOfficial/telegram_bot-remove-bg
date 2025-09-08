import os
import logging
import requests
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update, ChatAction
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Load environment variables from .env file
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY")

# Basic logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Hello! Send me any image and I will remove its background and send you back a transparent PNG.\n"
        "Tip: High-quality photos give better results."
    )

def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Just send me an image. I will remove the background and send you a PNG.\n"
        "If something goes wrong, please try again later."
    )

def _remove_bg(image_bytes: bytes) -> bytes:
    """
    Call remove.bg API and return background-removed image bytes (PNG).
    """
    url = "https://api.remove.bg/v1.0/removebg"
    headers = {"X-Api-Key": REMOVE_BG_API_KEY}
    files = {"image_file": ("image.png", image_bytes)}
    data = {"size": "auto"}  # options: auto, preview, etc.

    resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    if resp.status_code == 200:
        return resp.content
    else:
        # Log detailed error from API if available
        try:
            logger.error("remove.bg error: %s", resp.json())
        except Exception:
            logger.error("remove.bg non-JSON error, status=%s", resp.status_code)
        raise RuntimeError(f"remove.bg failed with status {resp.status_code}")

def handle_photo(update: Update, context: CallbackContext):
    if not REMOVE_BG_API_KEY:
        update.message.reply_text("Server configuration issue: REMOVE_BG_API_KEY is missing.")
        return

    message = update.message

    # Get the highest-resolution photo if sent as a photo
    photo_file = None
    if message.photo:
        photo = message.photo[-1]
        photo_file = photo.get_file()
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        photo_file = message.document.get_file()
    else:
        message.reply_text("Please send an image (photo or image document).")
        return

    try:
        # Show "uploading photo" status while processing
        context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO)

        # Download image bytes
        bio = BytesIO()
        photo_file.download(out=bio)
        bio.seek(0)

        # Call remove.bg
        removed = _remove_bg(bio.read())

        # Send result as a document (to preserve PNG transparency)
        result_bio = BytesIO(removed)
        result_bio.name = "no-bg.png"
        result_bio.seek(0)
        message.reply_document(result_bio, caption="Done ✅ Background removed.")

    except RuntimeError as e:
        logger.exception("remove.bg error")
        message.reply_text(f"Background removal failed: {e}")
    except Exception as e:
        logger.exception("Unexpected error")
        message.reply_text("Something went wrong. Please try again later.")

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing in environment/.env")
    if not REMOVE_BG_API_KEY:
        logger.warning("REMOVE_BG_API_KEY not set. The bot will not be able to process images.")

    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(MessageHandler(Filters.photo | Filters.document.category("image"), handle_photo))

    updater.start_polling(clean=True)
    logger.info("Bot is running. Press Ctrl+C to stop.")
    updater.idle()

if __name__ == "__main__":
    main()