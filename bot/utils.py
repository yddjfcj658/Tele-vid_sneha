import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from .config import *

async def animate_message(update: Update, context: ContextTypes.DEFAULT_TYPE, messages: list, duration: float = 0.5, target_message=None):
    """Edits a message sequentially to create an animation effect."""
    message = target_message
    if not message:
        if update.callback_query:
            message = update.callback_query.message
        elif update.message:
            message = update.message
        
    if not message:
        import logging
        logging.warning("No message object found to animate.")
        return

    for msg in messages:
        try:
            await message.edit_text(msg, parse_mode='Markdown')
            await asyncio.sleep(duration)
        except Exception as e:
            # Handle cases where message content is same or message deleted
            import logging
            logging.debug(f"Animation edit failed: {e}")
            continue

async def send_to_admin(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    """Sends a message to the admin chat."""
    import logging
    try:
        # Ensure ADMIN_CHAT_ID is an integer if it's a numeric string
        admin_id = ADMIN_CHAT_ID
        if isinstance(admin_id, str) and (admin_id.startswith('-') or admin_id.isdigit()):
            admin_id = int(admin_id)
            
        logging.info(f"Attempting to send admin notification to: {admin_id}")
        await context.bot.send_message(
            chat_id=admin_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logging.info("Admin notification sent successfully.")
    except Exception as e:
        logging.error(f"FAILED to send admin notification to {ADMIN_CHAT_ID}: {e}")
