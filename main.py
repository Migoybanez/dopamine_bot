import asyncio
import datetime
import gspread
import os
import openai
from google.oauth2.service_account import Credentials
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

# Constants
CHECKIN_INTERVAL_SECONDS = 30
SHEET_COLUMNS = {
    'USER_ID': 1,
    'USERNAME': 2,
    'DETOX_DAYS': 3,
    'FASTING_TARGET': 4,
    'GROUP': 5,
    'STATUS': 6,
    'REMINDER': 7,
    'MEDIA_ID': 8,
    'MEDIA_TYPE': 9,
    'REMINDER_SENT': 10,
    'SHARED_MILESTONES': 11
}

# Error message constants
ERROR_MESSAGES = {
    'NETWORK_ERROR': '⚠️ Network error. Please try again.',
    'INVALID_INPUT': '❌ Invalid input. Please try again.',
    'NOT_SUBSCRIBED': '⚠️ You\'re not subscribed to check-ins yet.',
    'ALREADY_SUBSCRIBED': '✅ You\'re already subscribed to check-ins.',
    'MEDIA_ERROR': '❌ Please send a valid audio, voice, video, or video note file.',
    'GROUP_SHARE_ERROR': '❌ Could not share in group. Please try again later.'
}

# OpenAI API setup
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# Timezone setup - PHT (Philippine Time)
PHT_TIMEZONE = datetime.timezone(datetime.timedelta(hours=8))  # UTC+8

def get_pht_now():
    """Get current time in Philippine Time"""
    return datetime.datetime.now(PHT_TIMEZONE)

def get_pht_date():
    """Get current date in Philippine Time"""
    return get_pht_now().strftime("%Y-%m-%d")

def get_pht_timestamp():
    """Get current timestamp in Philippine Time"""
    return get_pht_now().strftime("%Y-%m-%d %H:%M:%S")

# Reminder: Ensure you have a working internet connection and DNS can resolve both api.telegram.org and sheets.googleapis.com.
# If you see connection errors, check your network, DNS, VPN, or firewall settings.

# ✅ Google Sheets setup
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
gc = gspread.authorize(CREDS)
SHEET_ID = "1Oif-d33v0tMImy2-PyppqFwT9H2DfsIimYlswD3QOfQ"
worksheet = gc.open_by_key(SHEET_ID).sheet1

GROUP_CHAT_IDS = {
    "GameBreak": -1002568374429,
    "NoFap": -1002730320077,
    "ScreenBreak": -1002728977026
}

MEDIA_DIR = "user_commitments"
os.makedirs(MEDIA_DIR, exist_ok=True)

# ✅ Helper to get latest detox entry per user
def get_latest_entries_by_user(rows):
    if not rows:
        return []
    latest = {}
    for row in reversed(rows):
        if row.get('user_id') and row['user_id'] not in latest:
            latest[row['user_id']] = row
    return list(latest.values())

def sanitize_input(text):
    """Sanitize user input to prevent injection attacks"""
    if not text:
        return ""
    # Remove any potentially dangerous characters
    dangerous_chars = ['<', '>', '&', '"', "'", ';', '(', ')', '{', '}']
    for char in dangerous_chars:
        text = text.replace(char, '')
    return text.strip()[:100]  # Limit to 100 characters

def get_file_extension(media_type):
    """Get appropriate file extension for media type"""
    extensions = {
        'voice': '.ogg',
        'audio': '.mp3',
        'video': '.mp4',
        'video_note': '.mp4',
        'document': '.pdf'
    }
    return extensions.get(media_type, '.ogg')

async def get_chatgpt_response(user_question, user_context):
    """Get personalized response from ChatGPT based on user's habit context"""
    if not OPENAI_API_KEY:
        return "I'm sorry, I'm not able to provide personalized advice right now. Please try again later."
    
    try:
        # Build context-aware prompt
        habit_target = user_context.get('fasting_target', 'their habit')
        current_streak = user_context.get('current_streak', 0)
        group = user_context.get('group', 'None')
        
        system_prompt = f"""You are a supportive habit transformation coach helping someone break a bad habit. 

User Context:
- They are trying to break the habit of: {habit_target}
- Current streak: {current_streak} days
- Accountability group: {group}

Provide encouraging, practical advice that's specific to their situation. Keep responses concise (2-3 sentences max) and focus on actionable tips. Be supportive but realistic. Use emojis sparingly to keep it friendly.

If they ask about something unrelated to habit formation, motivation, or wellness, politely redirect them back to their habit goals."""

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"[ERROR] ChatGPT API error: {e}")
        return "I'm having trouble connecting to my advice system right now. Try asking me again in a moment!"

# ✅ Daily check-in sender with 3-day miss check
async def send_daily_checkins(app):
    print("[DEBUG] send_daily_checkins called")
    try:
        rows = worksheet.get_all_records()
    except Exception as e:
        print(f"[ERROR] Failed to get worksheet records: {e}")
        return
    
    latest_entries = get_latest_entries_by_user(rows)
    print(f"[DEBUG] Found {len(latest_entries)} active users")

    for row in latest_entries:
        try:
            if row.get("status", "").lower() == "stopped":
                print(f"[DEBUG] User {row.get('user_id', 'unknown')} is stopped, skipping")
                continue

            user_id = row.get('user_id')
            target = row.get('fasting_target', 'Unknown')
            username_display = f"@{row.get('username', '')}" if row.get('username') else "there"
            print(f"[DEBUG] Processing user {user_id} ({username_display})")

            # Check last 3 check-ins
            try:
                checkin_sheet = gc.open_by_key(SHEET_ID).worksheet("Daily Check-ins")
                history = checkin_sheet.get_all_records()
            except Exception as e:
                print(f"[DEBUG] Error getting check-in history: {e}")
                history = []

            # Get all check-ins for the user, most recent first
            user_history = [r for r in reversed(history) if str(r.get("user_id", "")) == str(user_id)]
            print(f"[DEBUG] User {user_id} has {len(user_history)} check-ins")
            
            # Check if user has at least one 'yes' check-in
            has_yes_checkin = any(r.get("status") == "yes" for r in user_history)
            print(f"[DEBUG] User {user_id} has_yes_checkin: {has_yes_checkin}")
            if has_yes_checkin:
                yes_checkins = [r for r in user_history if r.get("status") == "yes"]
                print(f"[DEBUG] User {user_id} has {len(yes_checkins)} 'yes' check-ins")
            
            # Get the last 3 check-ins (most recent first)
            last_3 = [r.get("status", "") for r in user_history[:3]]
            print(f"[DEBUG] Last 3 check-ins for user {user_id}: {last_3}")
            
            # Check if user has already checked in today (to avoid sending reminders right after they check in)
            today = get_pht_date()
            checked_in_today = False
            if user_history:
                latest_checkin = user_history[0]  # Most recent check-in
                latest_timestamp = latest_checkin.get("timestamp", "")
                if isinstance(latest_timestamp, str) and latest_timestamp.startswith(today):
                    checked_in_today = True
            print(f"[DEBUG] User {user_id} checked in today: {checked_in_today}")
            
            reminder_sent = row.get("reminder_sent", "")
            media_type = row.get("media_type", "video")  # default to video for backward compatibility
            print(f"[DEBUG] User {user_id} reminder_sent: '{reminder_sent}', media_type: '{media_type}'")
            
            # Calculate current streak
            current_streak = 0
            for entry in user_history:
                if entry.get("status") == "yes":
                    current_streak += 1
                else:
                    break
            
            # Always send the daily check-in with streak count
            if current_streak > 0:
                text = f"🔁 Daily Check-In\n\nHey {username_display}! You're on a *{current_streak}-day streak*! 🎉\n\nWere you able to stick to your detox from *{target}* today?"
            else:
                text = f"🔁 Daily Check-In\n\nHey {username_display}! Were you able to stick to your detox from *{target}* today?"
            
            try:
                await app.bot.send_message(
                    chat_id=int(user_id),
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("\u2705 Yes", callback_data=f"checkin_yes_{user_id}"),
                            InlineKeyboardButton("\u274C No", callback_data=f"checkin_no_{user_id}")
                        ]
                    ])
                )
                print(f"[DEBUG] Sent daily check-in to user {user_id}")
            except Exception as e:
                print(f"❌ Could not message {user_id}: {e}")
                
        except Exception as e:
            print(f"[ERROR] Error processing user {row.get('user_id', 'unknown')}: {e}")
            continue
        
        # Reminder logic moved to handle_checkin_response for immediate delivery

# Google Sheet columns (expected order):
# user_id | username | detox_days | fasting_target | group | status | reminder | media_id | reminder_sent | media_type

# --- Onboarding Handlers with State Tracking ---

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.effective_user or not update.message:
            return
        
        if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
            context.user_data = {}
        
        user_id = str(update.effective_user.id)
        rows = worksheet.get_all_records()
        for i, row in enumerate(rows):
            if str(row.get('user_id', '')) == user_id:
                worksheet.update_cell(i + 2, SHEET_COLUMNS['STATUS'], "active")
                break
        context.user_data['onboarding_state'] = 'habit'
        await update.message.reply_text(
            "👋 *Welcome to your habit transformation journey!*\n\n"
            "I'm here to help you build better habits and break the ones that aren't serving you.\n\n"
            "🎯 *What bad habit are you most excited to take a break from right now?*\n\n"
            "Some popular examples:\n"
            "• 🎮 Gaming\n"
            "• 📱 Social media (TikTok, Instagram, etc.)\n"
            "• 🍬 Sugar/junk food\n"
            "• 🚬 Smoking\n"
            "• 🍺 Alcohol\n"
            "• 📱 Mindless scrolling\n\n"
            "Tell me what you'd like to work on by typing it below!",
            parse_mode="Markdown"
        )
        context.user_data["detox_days"] = "Unknown"
    except Exception as e:
        print(f"[ERROR] Error in start function: {e}")
        if update.message:
            await update.message.reply_text(ERROR_MESSAGES['NETWORK_ERROR'])

async def capture_fasting_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    print("capture_fasting_target called, onboarding_state:", context.user_data.get('onboarding_state'))
    if context.user_data.get('onboarding_state') != 'habit':
        return
    if not update.message or not hasattr(update.message, 'text') or not update.message.text:
        if update.message and hasattr(update.message, 'reply_text'):
            await update.message.reply_text("❓ Please tell me what habit you want to fast from.")
        return
    
    # Sanitize and validate input
    habit_input = sanitize_input(update.message.text)
    if not habit_input:
        if update.message and hasattr(update.message, 'reply_text'):
            await update.message.reply_text(ERROR_MESSAGES['INVALID_INPUT'])
        return
    
    context.user_data["fasting_target"] = habit_input
    context.user_data['onboarding_state'] = 'reminder_consent'
    if update.message and hasattr(update.message, 'reply_text'):
        await update.message.reply_text(
            "📅 Would you like me to send you daily check-in reminders?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, keep me on track", callback_data="reminder_yes"),
                    InlineKeyboardButton("🙅‍♂️ No, I'll check in myself", callback_data="reminder_no")
                ]
            ])
        )

async def handle_reminder_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    if context.user_data.get('onboarding_state') != 'reminder_consent':
        return
    query = update.callback_query
    if not query or not hasattr(query, 'data'):
        return
    await query.answer()
    context.user_data["reminder_consent"] = query.data == "reminder_yes"
    
    if query.data == "reminder_no":
        # User declined daily check-ins, end onboarding
        context.user_data['onboarding_state'] = None
        await query.edit_message_text("👋 No problem! If you change your mind, just type /start again to set up daily check-ins.")
        return
    
    # User agreed to daily check-ins, inform them about timing
    context.user_data['onboarding_state'] = 'media_upload'
    await query.edit_message_text(
        "✅ Perfect! I'll check in with you every morning at 9 AM to ask about your progress from the day before.\n\n"
        "🎙️ 🔴 *Highly recommended*: Do you want to record a voice, video, or video note message to yourself as a commitment?\n\n" +
        "If you miss 3 days in a row, I'll send it back to you as a reminder of your why.\n\n" +
        "Send it here or type /skip if you want to skip this."
    )
    context.user_data["waiting_for_media"] = True

async def handle_media_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    print("handle_media_upload called, onboarding_state:", context.user_data.get('onboarding_state'))
    if context.user_data.get('onboarding_state') != 'media_upload':
        return
    if not context.user_data.get("waiting_for_media"):
        return
    
    try:
        file = None
        media_type = None
        if update.message:
            if hasattr(update.message, 'audio') and update.message.audio:
                file = update.message.audio
                media_type = "audio"
            elif hasattr(update.message, 'voice') and update.message.voice:
                file = update.message.voice
                media_type = "voice"
            elif hasattr(update.message, 'video') and update.message.video:
                file = update.message.video
                media_type = "video"
            elif hasattr(update.message, 'video_note') and update.message.video_note:
                file = update.message.video_note
                media_type = "video_note"
            elif hasattr(update.message, 'document') and update.message.document:
                file = update.message.document
                media_type = "document"
        
        if not file:
            if update.message and hasattr(update.message, 'reply_text'):
                await update.message.reply_text(ERROR_MESSAGES['MEDIA_ERROR'])
            return
        
        file_id = file.file_id
        if not update.effective_user:
            return
        user_id = str(update.effective_user.id)
        
        # Delete old media file if it exists with proper extension
        file_extension = get_file_extension(media_type)
        old_file_path = os.path.join(MEDIA_DIR, f"{user_id}{file_extension}")
        if os.path.exists(old_file_path):
            try:
                os.remove(old_file_path)
                print(f"[DEBUG] Deleted old media file for user {user_id}.")
            except Exception as e:
                print(f"[DEBUG] Could not delete old media file for user {user_id}: {e}")
        
        context.user_data["reminder_media_id"] = file_id
        context.user_data["reminder_media_type"] = media_type
        context.user_data["waiting_for_media"] = False
        context.user_data['onboarding_state'] = 'group'
        if update.message and hasattr(update.message, 'reply_text'):
            await update.message.reply_text("🎧 Got it! I'll keep this and send it if you miss 3 days in a row.")
        await ask_group(update, context)
        
    except Exception as e:
        print(f"[ERROR] Error in handle_media_upload: {e}")
        if update.message and hasattr(update.message, 'reply_text'):
            await update.message.reply_text(ERROR_MESSAGES['MEDIA_ERROR'])

async def skip_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    if context.user_data.get('onboarding_state') != 'media_upload':
        return
    context.user_data["reminder_media_id"] = None
    context.user_data["waiting_for_media"] = False
    context.user_data['onboarding_state'] = 'group'
    if update.message and hasattr(update.message, 'reply_text'):
        await update.message.reply_text("👍 No worries. We'll skip this part.")
    await ask_group(update, context)

async def ask_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("🎮 GameBreak", callback_data="group_GameBreak")],
        [InlineKeyboardButton("⛔ NoFap", callback_data="group_NoFap")],
        [InlineKeyboardButton("📵 ScreenBreak", callback_data="group_ScreenBreak")],
        [InlineKeyboardButton("🙅 Not part of any group", callback_data="group_None")]
    ]
    if update.message and hasattr(update.message, 'reply_text'):
        await update.message.reply_text(
            "Which accountability group are you part of?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif update.callback_query and hasattr(update.callback_query, 'message') and update.callback_query.message and hasattr(update.callback_query.message, 'reply_text'):
        await update.callback_query.message.reply_text(
            "Which accountability group are you part of?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def handle_group_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    if context.user_data.get('onboarding_state') != 'group':
        return
    query = update.callback_query
    if not query or not hasattr(query, 'data') or not hasattr(query, 'edit_message_text'):
        return
    await query.answer()
    group = query.data.replace("group_", "") if query.data else "None"
    context.user_data["group"] = group
    context.user_data['onboarding_state'] = None
    
    if group == "None":
        await query.edit_message_text("👍 Got it! We'll keep your progress between us. No group sharing unless you want to.\n\nGive me a few seconds to initialize and begin...")
    else:
        await query.edit_message_text(f"Great! You're in the {group} group.\n\nGive me a few seconds to initialize and begin...")
    
    await finalize_onboarding(update, context)

# --- End Onboarding Handlers ---

# In finalize_onboarding, update user row if exists, else append
async def finalize_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    
    try:
        if not update.effective_user:
            return
            
        user_id = update.effective_user.id if hasattr(update.effective_user, 'id') else ""
        username = update.effective_user.username if hasattr(update.effective_user, 'username') and update.effective_user.username else "No username"
        detox_days = context.user_data.get("detox_days", "Unknown")
        target = context.user_data.get("fasting_target", "Unknown")
        group = context.user_data.get("group", "None")
        reminder = "yes" if context.user_data.get("reminder_consent") else "no"
        media_id = context.user_data.get("reminder_media_id", "")
        media_type = context.user_data.get("reminder_media_type", "")
        
        # Check if user already exists
        rows = worksheet.get_all_records()
        found = False
        for i, row in enumerate(rows):
            if str(row.get('user_id', '')) == str(user_id):
                worksheet.update_cell(i + 2, SHEET_COLUMNS['USERNAME'], str(username))
                worksheet.update_cell(i + 2, SHEET_COLUMNS['DETOX_DAYS'], str(detox_days))
                worksheet.update_cell(i + 2, SHEET_COLUMNS['FASTING_TARGET'], str(target))
                worksheet.update_cell(i + 2, SHEET_COLUMNS['GROUP'], str(group))
                worksheet.update_cell(i + 2, SHEET_COLUMNS['STATUS'], "active")
                worksheet.update_cell(i + 2, SHEET_COLUMNS['REMINDER'], str(reminder))
                worksheet.update_cell(i + 2, SHEET_COLUMNS['MEDIA_ID'], str(media_id))
                worksheet.update_cell(i + 2, SHEET_COLUMNS['MEDIA_TYPE'], str(media_type))
                found = True
                break
        if not found:
            worksheet.append_row([
                str(user_id), str(username), str(detox_days), str(target),
                str(group), "active", str(reminder), str(media_id), str(media_type)
            ])
        # Always send the final onboarding message
        final_msg = "🚀 You're all set! I'll check in with you starting tomorrow at 9 AM. Have a great rest of your day!"
        if update.message and hasattr(update.message, 'reply_text'):
            await update.message.reply_text(final_msg)
        elif update.callback_query and update.callback_query.message and hasattr(update.callback_query.message, 'reply_text'):
            await update.callback_query.message.reply_text(final_msg)
        context.user_data['onboarding_state'] = None
        
    except Exception as e:
        print(f"[ERROR] Error in finalize_onboarding: {e}")
        if update.message and hasattr(update.message, 'reply_text'):
            await update.message.reply_text(ERROR_MESSAGES['NETWORK_ERROR'])

# ✅ Save voice/video commitment
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    file = update.message.voice if update.message else None
    if not file and update.message:
        file = update.message.video_note
    if not file:
        if update.message:
            await update.message.reply_text("❌ Please send a *voice* or *video note*.", parse_mode="Markdown")
        return
    file_path = os.path.join(MEDIA_DIR, f"{user_id}.ogg")
    new_file = await file.get_file()
    await new_file.download_to_drive(file_path)
    if update.message:
        await update.message.reply_text("✅ Got your commitment video. I'll send this back to you if you miss 3 days in a row ✊")

# --- Add debug print to check-in handler ---
async def handle_checkin_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[DEBUG] handle_checkin_response called. update:", update)
    query = update.callback_query
    if not query or not hasattr(query, 'data') or not query.data:
        print("[DEBUG] No callback query or data found.")
        return
    print(f"[DEBUG] Callback data received: {query.data}")
    await query.answer()
    
    try:
        status, user_id = query.data.split("_")[1:]
        print(f"[DEBUG] Parsed status: {status}, user_id: {user_id}")
        
        # Check if user is stopped - if so, ignore the check-in response
        all_rows = worksheet.get_all_records()
        user_row = next((r for r in all_rows if str(r.get('user_id', '')) == str(user_id)), None)
        if user_row and user_row.get("status", "active") == "stopped":
            print(f"[DEBUG] User {user_id} is stopped, ignoring check-in response")
            await query.edit_message_text("🛑 You're unsubscribed from check-ins. Use /start to resubscribe.")
            return
        
        timestamp = get_pht_timestamp()
        try:
            checkin_sheet = gc.open_by_key(SHEET_ID).worksheet("Daily Check-ins")
        except Exception as e:
            checkin_sheet = gc.open_by_key(SHEET_ID).add_worksheet(title="Daily Check-ins", rows=1000, cols=5)
            checkin_sheet.append_row(["user_id", "status", "timestamp"])
        checkin_sheet.append_row([user_id, status, timestamp])
        
        # Different response messages based on their choice
        if status == "yes":
            await query.edit_message_text("✅ Got it! Keep going.")
        else:
            await query.edit_message_text("👍 No worries! Tomorrow is a fresh start. You've got this!")
        
        # Check if this was the 3rd 'no' in a row and send reminder immediately
        if status == "no":
            # Get all check-ins for this user, most recent first
            try:
                history = checkin_sheet.get_all_records()
            except Exception as e:
                history = []
            user_history = [r for r in reversed(history) if str(r.get("user_id", "")) == str(user_id)]
            
            # Check if user has at least one 'yes' check-in
            has_yes_checkin = any(r.get("status") == "yes" for r in user_history)
            
            # Get the last 3 check-ins (most recent first)
            last_3 = [r.get("status", "") for r in user_history[:3]]
            print(f"[DEBUG] After 'no' check-in - User {user_id} last_3: {last_3}")
            
            # Get user's reminder settings
            all_rows = worksheet.get_all_records()
            user_row = next((r for r in all_rows if str(r.get('user_id', '')) == str(user_id)), None)
            reminder_sent = user_row.get("reminder_sent", "") if user_row else ""
            media_id = str(user_row.get("media_id", "")) if user_row else ""
            media_type = user_row.get("media_type", "video") if user_row else "video"
            
            # Send reminder if this was the 3rd 'no' in a row
            if (has_yes_checkin and len(last_3) == 3 and last_3 == ["no", "no", "no"] and 
                reminder_sent != "yes" and media_id and media_type in ["voice", "video_note", "audio", "document", "video"]):
                print(f"[DEBUG] Sending immediate reminder to user {user_id} after 3rd 'no'")
                try:
                    await context.bot.send_message(int(user_id), text="📼 Here's a message you recorded for yourself. Remember why you started.")
                    if media_type == "voice":
                        await context.bot.send_voice(int(user_id), voice=media_id)
                    elif media_type == "video_note":
                        await context.bot.send_video_note(int(user_id), video_note=media_id)
                    elif media_type == "audio":
                        await context.bot.send_audio(int(user_id), audio=media_id)
                    elif media_type == "document":
                        await context.bot.send_document(int(user_id), document=media_id)
                    else:
                        await context.bot.send_video(int(user_id), video=media_id)
                    print(f"[DEBUG] Successfully sent immediate reminder to user {user_id}")
                    
                    # Set reminder_sent to 'yes' in the sheet
                    for i, r in enumerate(all_rows):
                        if str(r.get('user_id', '')) == str(user_id):
                            worksheet.update_cell(i + 2, SHEET_COLUMNS['REMINDER_SENT'], "yes")
                            print(f"[DEBUG] Set reminder_sent to 'yes' for user {user_id}")
                            break
                except Exception as e:
                    print(f"⚠️ Could not send immediate reminder to {user_id}: {e}")
        
        # Reset reminder_sent if user checks in with 'yes'
        if status == "yes":
            all_rows = worksheet.get_all_records()
            for i, r in enumerate(all_rows):
                if str(r.get('user_id', '')) == str(user_id):
                    worksheet.update_cell(i + 2, SHEET_COLUMNS['REMINDER_SENT'], "")
                    break
            # --- Milestone streak logic ---
            # Get all check-ins for this user, most recent first
            try:
                history = checkin_sheet.get_all_records()
            except Exception as e:
                history = []
            user_history = [r for r in reversed(history) if str(r.get("user_id", "")) == str(user_id)]
            streak = 0
            for entry in user_history:
                if entry.get("status") == "yes":
                    streak += 1
                else:
                    break
            print(f"[DEBUG] User {user_id} has a streak of {streak} days")
            milestones = [3, 7, 14, 30, 60, 90]
            if streak in milestones:
                # Check if user has already been asked about this milestone
                user_row = next((r for r in all_rows if str(r.get('user_id', '')) == str(user_id)), None)
                shared_milestones = str(user_row.get("shared_milestones", "")) if user_row else ""
                shared_list = shared_milestones.split(",") if shared_milestones else []
                shared_list = [int(x.strip()) for x in shared_list if x.strip().isdigit()]
                
                if streak not in shared_list:
                    print(f"[DEBUG] User {user_id} hit milestone {streak} for the first time!")
                    # Find user's group and username
                    group = str(user_row.get("group", "None")) if user_row else "None"
                    username = user_row.get("username", "") if user_row else ""
                    print(f"[DEBUG] User {user_id} group: {group}, username: {username}")
                    
                    # Skip sharing prompt if user is not part of any group
                    if group == "None":
                        print(f"[DEBUG] User {user_id} is not part of any group, skipping sharing prompt")
                        # Still record this milestone as "shared" so they don't get asked again
                        shared_list.append(streak)
                        new_shared_milestones = ",".join(map(str, shared_list))
                        for i, r in enumerate(all_rows):
                            if str(r.get('user_id', '')) == str(user_id):
                                worksheet.update_cell(i + 2, SHEET_COLUMNS['SHARED_MILESTONES'], new_shared_milestones)
                                print(f"[DEBUG] Updated shared_milestones for user {user_id}: {new_shared_milestones}")
                                break
                        return
                    
                    try:
                        share_markup = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("Share in Group", callback_data=f"streak_share_share_{streak}"),
                                InlineKeyboardButton("Keep Private", callback_data=f"streak_share_private_{streak}")
                            ]
                        ])
                        await context.bot.send_message(
                            chat_id=int(user_id),
                            text=f"🎉 Congrats on your {streak}-day streak! Would you like to share this achievement in your group?",
                            reply_markup=share_markup
                        )
                        print(f"[DEBUG] Sent streak milestone message to user {user_id}")
                    except Exception as e:
                        print(f"Error sending share prompt: {e}")
                else:
                    print(f"[DEBUG] User {user_id} already hit milestone {streak} before, not asking again")
            else:
                print(f"[DEBUG] User {user_id} streak {streak} is not a milestone")
                
    except Exception as e:
        print(f"[ERROR] Error in handle_checkin_response: {e}")
        if query and hasattr(query, 'edit_message_text'):
            await query.edit_message_text(ERROR_MESSAGES['NETWORK_ERROR'])

# ✅ /stop command
async def stop_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.effective_user:
            return
            
        user_id = str(update.effective_user.id)
        rows = worksheet.get_all_records()
        for i, row in enumerate(rows):
            if str(row.get("user_id", "")) == user_id:
                worksheet.update_cell(i + 2, SHEET_COLUMNS['STATUS'], "stopped")
                if update.message:
                    await update.message.reply_text("🛑 You've been unsubscribed from daily check-ins.")
                return
        if update.message:
            await update.message.reply_text(ERROR_MESSAGES['NOT_SUBSCRIBED'])
    except Exception as e:
        print(f"[ERROR] Error in stop_tracking: {e}")
        if update.message:
            await update.message.reply_text(ERROR_MESSAGES['NETWORK_ERROR'])

# ✅ /reset command
async def reset_streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.effective_user:
            return
            
        user_id = str(update.effective_user.id)
        timestamp = get_pht_timestamp()

        try:
            checkin_sheet = gc.open_by_key(SHEET_ID).worksheet("Daily Check-ins")
        except Exception as e:
            checkin_sheet = gc.open_by_key(SHEET_ID).add_worksheet(title="Daily Check-ins", rows=1000, cols=5)
            checkin_sheet.append_row(["user_id", "status", "timestamp"])

        checkin_sheet.append_row([user_id, "reset", timestamp])
        
        # Clear reminder_sent field so user can get reminders again
        all_rows = worksheet.get_all_records()
        for i, r in enumerate(all_rows):
            if str(r.get('user_id', '')) == str(user_id):
                worksheet.update_cell(i + 2, SHEET_COLUMNS['REMINDER_SENT'], "")
                print(f"[DEBUG] Reset reminder_sent for user {user_id} after streak reset")
                break
        
        if update.message:
            await update.message.reply_text("🔄 Your streak has been reset to Day 1!")
    except Exception as e:
        print(f"[ERROR] Error in reset_streak: {e}")
        if update.message:
            await update.message.reply_text(ERROR_MESSAGES['NETWORK_ERROR'])

# Place handle_share_streak above main
async def handle_share_streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    
    await query.answer()
    user_id = str(update.effective_user.id) if update.effective_user else None
    if not user_id:
        return
    
    group = query.data.replace("share_", "")
    
    try:
        # Get user's latest data
        rows = worksheet.get_all_records()
        user_data = None
        for row in rows:
            if str(row.get('user_id', '')) == user_id:
                user_data = row
                break
        
        if not user_data:
            await query.edit_message_text("❌ Could not find your data. Please try again.")
            return
        
        # Get current streak
        try:
            checkin_sheet = gc.open_by_key(SHEET_ID).worksheet("Daily Check-ins")
            history = checkin_sheet.get_all_records()
        except Exception as e:
            print(f"[DEBUG] Error getting check-in history: {e}")
            await query.edit_message_text("❌ Could not get your streak data. Please try again.")
            return
        
        user_history = [r for r in reversed(history) if str(r.get("user_id", "")) == str(user_id)]
        current_streak = 0
        for entry in user_history:
            if entry.get("status") == "yes":
                current_streak += 1
            else:
                break
        
        if current_streak < 3:
            await query.edit_message_text("🎉 You need at least 3 days to share a milestone! Keep going!")
            return
        
        # Share in group
        if group in GROUP_CHAT_IDS:
            group_chat_id = GROUP_CHAT_IDS[group]
            username = ""
            if update.effective_user:
                username = update.effective_user.username or update.effective_user.first_name or "Anonymous"
            target = user_data.get('fasting_target', 'Unknown')
            
            share_message = f"🎉 *Milestone Alert!*\n\n@{username} just hit a *{current_streak}-day streak* breaking free from {target}! 🚀\n\nKeep inspiring the community!"
            
            try:
                await context.bot.send_message(
                    chat_id=group_chat_id,
                    text=share_message,
                    parse_mode="Markdown"
                )
                await query.edit_message_text(f"✅ Shared your {current_streak}-day milestone in {group}! 🎉")
                
                # Mark this milestone as shared
                for i, row in enumerate(rows):
                    if str(row.get('user_id', '')) == user_id:
                        worksheet.update_cell(i + 2, SHEET_COLUMNS['SHARED_MILESTONES'], f"{current_streak}")
                        break
                        
            except Exception as e:
                print(f"[ERROR] Could not share in group: {e}")
                await query.edit_message_text(ERROR_MESSAGES['GROUP_SHARE_ERROR'])
        else:
            await query.edit_message_text("❌ Invalid group selection.")
            
    except Exception as e:
        print(f"[ERROR] Error in handle_share_streak: {e}")
        await query.edit_message_text("❌ Something went wrong. Please try again.")

async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle general messages and provide ChatGPT responses for questions"""
    if not update.message or not update.message.text:
        return
    
    # Skip if user is in onboarding
    if hasattr(context, 'user_data') and context.user_data.get('onboarding_state'):
        return
    
    # Skip if it's a command
    if update.message.text.startswith('/'):
        return
    
    if not update.effective_user:
        return
    
    user_id = str(update.effective_user.id)
    
    # Get user context from Google Sheets
    try:
        rows = worksheet.get_all_records()
        user_data = None
        for row in rows:
            if str(row.get('user_id', '')) == user_id:
                user_data = row
                break
        
        if not user_data:
            return  # User not in system, ignore
        
        # Get current streak
        try:
            checkin_sheet = gc.open_by_key(SHEET_ID).worksheet("Daily Check-ins")
            history = checkin_sheet.get_all_records()
        except Exception as e:
            print(f"[DEBUG] Error getting check-in history: {e}")
            history = []
        
        user_history = [r for r in reversed(history) if str(r.get("user_id", "")) == str(user_id)]
        current_streak = 0
        for entry in user_history:
            if entry.get("status") == "yes":
                current_streak += 1
            else:
                break
        
        # Build user context
        user_context = {
            'fasting_target': user_data.get('fasting_target', 'Unknown') if user_data else 'Unknown',
            'current_streak': current_streak,
            'group': user_data.get('group', 'None') if user_data else 'None'
        }
        
        # Check if message looks like a question (contains question words or ends with ?)
        question_indicators = ['what', 'how', 'why', 'when', 'where', 'which', 'who', 'can you', 'could you', 'help', 'advice', 'tip', 'struggle', 'difficult', 'motivation', 'relapse']
        message_lower = update.message.text.lower()
        
        is_question = (
            update.message.text.endswith('?') or
            any(indicator in message_lower for indicator in question_indicators)
        )
        
        if is_question:
            # Show typing indicator
            if update.effective_chat:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            
            # Get ChatGPT response
            response = await get_chatgpt_response(update.message.text, user_context)
            
            await update.message.reply_text(response)
        
    except Exception as e:
        print(f"[ERROR] Error in handle_general_message: {e}")
        # Don't send error message to user, just log it

# ✅ Start app
if __name__ == '__main__':
    app = ApplicationBuilder().token("7070152877:AAEIfwdxiopaawZ-gb55LhabANLgXdYzG-Y").build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_tracking))
    app.add_handler(CommandHandler("reset", reset_streak))
    app.add_handler(CallbackQueryHandler(handle_checkin_response, pattern="^checkin_"))
    app.add_handler(CallbackQueryHandler(handle_reminder_consent, pattern="^reminder_"))
    app.add_handler(CommandHandler("skip", skip_media))
    app.add_handler(CallbackQueryHandler(handle_group_selection, pattern="group_"))
    # Register media handler BEFORE text handler
    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VIDEO_NOTE,
        handle_media_upload
    ))
    # Register text handler after media handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, capture_fasting_target))
    app.add_handler(CallbackQueryHandler(handle_share_streak, pattern="^share_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_general_message))

    loop = asyncio.get_event_loop()
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(send_daily_checkins(app), loop), 'interval', seconds=CHECKIN_INTERVAL_SECONDS)
    scheduler.start()

    print("✅ Bot is running... waiting for Telegram messages.")
    app.run_polling()
