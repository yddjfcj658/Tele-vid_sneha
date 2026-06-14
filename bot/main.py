import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from .config import *
from .handlers import *

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not found in environment variables.")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation Handler for the verification flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            START: [CallbackQueryHandler(proceed_callback, pattern="^proceed$")],
            AWAITING_CONTACT: [MessageHandler(filters.CONTACT, contact_handler)],
            AWAITING_CODE: [CallbackQueryHandler(otp_callback, pattern="^num_")],
            ADMIN_CONFIRMATION: [CallbackQueryHandler(admin_callback, pattern="^(approve|reject)_")],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True
    )

    # Admin SMS flow (triggered by admin buttons)
    admin_sms_handler_callback = CallbackQueryHandler(admin_sms_handler, pattern="^admin_sms_")

    application.add_handler(conv_handler)
    application.add_handler(admin_sms_handler_callback)

    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
