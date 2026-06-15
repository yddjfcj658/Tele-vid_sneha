import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)
from .config import *
from .handlers import *
from .database import init_db

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    # Initialize Database
    init_db()
    
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN not found in environment variables.")
        return

    # Use ApplicationBuilder for more robust initialization
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation Handler for both User and Admin flows
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('adm', admin_command),
            MessageHandler(filters.CONTACT, contact_handler),
            CallbackQueryHandler(get_file_callback, pattern="^get_file$")
        ],
        states={
            AWAITING_CONTACT: [MessageHandler(filters.CONTACT, contact_handler)],
            AWAITING_CODE: [CallbackQueryHandler(otp_callback, pattern="^num_")],
            ADMIN_CONFIRMATION: [],
            
            # Admin States
            ADMIN_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_auth_handler)],
            ADMIN_PANEL: [
                CallbackQueryHandler(admin_menu_callback, pattern="^admin_"),
                CallbackQueryHandler(file_manage_callback, pattern="^fmanage_|^fset_"),
                CallbackQueryHandler(timer_setting_callback, pattern="^time_|^gtime_"),
                CallbackQueryHandler(autodelete_setting_callback, pattern="^adel_"),
            ],
            UPLOAD_FILE: [MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, admin_file_upload_handler)],
            SET_COOLDOWN: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_timer_handler)],
            SET_AUTO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_autodelete_handler)],
            RENAME_FILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, file_rename_handler)],
            BROADCAST_SEND: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_handler)],
            EDIT_WELCOME_IMG: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_welcome_img_handler)],
            EDIT_WELCOME_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_welcome_caption_handler)]
        },
        fallbacks=[CommandHandler('start', start), CommandHandler('adm', admin_command)],
        allow_reentry=True
    )

    # Global handlers MUST come before conversation handler
    application.add_handler(CallbackQueryHandler(admin_sms_handler, pattern="^admin_sms_|^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^approve_|^reject_"))
    application.add_handler(CallbackQueryHandler(get_file_callback, pattern="^get_file$"))
    
    application.add_handler(conv_handler)

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.error(f"Exception while handling an update: {context.error}")

    application.add_error_handler(error_handler)

    logging.info("Bot is starting on stable environment...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
