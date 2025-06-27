import asyncio
import datetime
import gspread
import os
import openai
from google.oauth2.service_account import Credentials
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

print("[DEBUG] Script loaded (top of file)")

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
    'SHARED_MILESTONES': 11,
    'FEEDBACK_COMPLETED': 12
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
OPENAI_API_KEY = "***REMOVED***proj-aFS56sYLZquLhM-x6v9HEHXlWhSMt_pDvlDry7sccDRnBNDpwodNYk-V-OJHV2eb_B_xfkAox3T3BlbkFJaGxVggbgQl-f6UUrgBOoKHvNlw1sPSN8ZRW6xMT6kojGIjRORJfX3y-SRN4xPys21UiKt9E7oA"
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
CREDENTIALS_FILE = os.getenv('DOPAMINE_BOT_CREDENTIALS', "dopamine_bot_credentials.json")
CREDS = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
gc = gspread.authorize(CREDS)
SHEET_ID = "1Oif-d33v0tMImy2-PyppqFwT9H2DfsIimYlswD3QOfQ"
worksheet = gc.open_by_key(SHEET_ID).sheet1

# Feedback tab setup
try:
    feedback_sheet = gc.open_by_key(SHEET_ID).worksheet("Feedback")
except Exception:
    feedback_sheet = gc.open_by_key(SHEET_ID).add_worksheet(title="Feedback", rows=1000, cols=10)
    feedback_sheet.append_row(["user_id", "username", "milestone", "question", "answer", "timestamp", "permission"])

# Milestone streaks to trigger feedback
MILESTONE_DAYS = [1, 7, 14, 30, 60, 90]

# Milestone questions
MILESTONE_QUESTIONS = {
    1: [
        {"q": "🧠 On a scale of 1–5, how focused have you felt lately? (1 = totally distracted, 5 = laser focused)", "type": "scale"},
        {"q": "💪 How often do you feel in control of your impulses? (1–5, 1 = always impulsive, 5 = total self-control)", "type": "scale"},
        {"q": "⏰ On a typical day, about how many hours do you spend on the habit that you want to fast on? (e.g., 0.5, 2, 6)", "type": "number"}
    ],
    3: [
        {"q": "🤖 Has having this daily accountability bot helped you keep your 3-day streak so far?", "type": "yesno"}
    ],
    7: [
        {"q": "🧠 On a scale of 1–5, how focused have you felt lately? (1 = totally distracted, 5 = laser focused)", "type": "scale"},
        {"q": "💪 How often do you feel in control of your impulses? (1–5, 1 = always impulsive, 5 = total self-control)", "type": "scale"},
        {"q": "⏰ Has the time you spent on your bad habit significantly decreased since you started this course or used this bot?", "type": "yesno"}
    ],
    14: [
        {"q": "🧠 On a scale of 1–5, how focused have you felt lately? (1 = totally distracted, 5 = laser focused)", "type": "scale"},
        {"q": "💪 How often do you feel in control of your impulses? (1–5, 1 = always impulsive, 5 = total self-control)", "type": "scale"},
        {"q": "⏰ Has the time you spent on your bad habit significantly decreased since you started this course or used this bot?", "type": "yesno"}
    ],
    30: [
        {"q": "🧠 On a scale of 1–5, how focused have you felt lately? (1 = totally distracted, 5 = laser focused)", "type": "scale"},
        {"q": "💪 How often do you feel in control of your impulses? (1–5, 1 = always impulsive, 5 = total self-control)", "type": "scale"},
        {"q": "⏰ Has the time you spent on your bad habit significantly decreased since you started this course or used this bot?", "type": "yesno"}
    ],
    60: [
        {"q": "🧠 On a scale of 1–5, how focused have you felt lately? (1 = totally distracted, 5 = laser focused)", "type": "scale"},
        {"q": "💪 How often do you feel in control of your impulses? (1–5, 1 = always impulsive, 5 = total self-control)", "type": "scale"},
        {"q": "⏰ Has the time you spent on your bad habit significantly decreased since you started this course or used this bot?", "type": "yesno"}
    ],
    90: [
        {"q": "🧠 On a scale of 1–5, how focused have you felt lately? (1 = totally distracted, 5 = laser focused)", "type": "scale"},
        {"q": "💪 How often do you feel in control of your impulses? (1–5, 1 = always impulsive, 5 = total self-control)", "type": "scale"},
        {"q": "⏰ Has the time you spent on your bad habit significantly decreased since you started this course or used this bot?", "type": "yesno"}
    ],
}

# Track pending feedback in user_data: context.user_data['pending_feedback'] = {"milestone": 7, "q_idx": 0, ...}

GROUP_CHAT_IDS = {
    "GameBreak": -1002568374429,
    "NoFap": -1002730320077,
    "ScreenBreak": -1002728977026,
    "General": -1002602987021,
    "Moneytalk": -1002689624093
}

# Welcome messages for each group
WELCOME_MESSAGES = {
    "GameBreak": """🎮 Hey @{username}, welcome to GAMEBREAK!

The support group for gamers who finally said: "Tama na, one last game forever na 'to." 😅

Here, we help each other quit unhealthy gaming habits and turn that energy into something productive — building skills, starting hustles, or just getting your life back.

Wanna start your detox streak today? Click the button below or dm me /start to log Day 1 and track your wins. 👊

Message me if you need anything else! 💪""",

    "ScreenBreak": """👁‍🗨 Yo @{username}! Welcome to SCREEN BREAK — where we unplug to upgrade.

This group is for anyone stuck in doomscrolling, content overload, or screen fatigue who's ready to take back control of their time and mind.

Every week, we drop thought-provoking prompts to remind you to live more offline and move with intention.

Wanna start your detox streak today? Click the button below or dm me /start to log Day 1 and track your wins. 👊

Message me if you need anything else! 💪""",

    "NoFap": """🛡️ Hey @{username}, welcome to the NOFAP group!

This space is for warriors on a mission — transmuting urges into strength, purpose, and real power.

⚔️ Expect deep convos, warrior memes, and reminders that you're not alone in this fight.

💪 Ready to track your streak and start the transformation? Tap the button or DM me /start — I'll log your progress and check in daily like your personal accountability partner.

Message me if you need anything else! 💪""",

    "General": """⚡ Yo @{username}, welcome to the Transmutation Method community!

This is the main hub where we post the latest updates, content drops, announcements, and reminders about all things related to the movement.

🧭 Whether you're here to detox from dopamine traps or build the next version of yourself, you're in good company. 🙌

📍 Make sure to also join the focused groups depending on your personal goals:
🎮 Gaming Detox – Join GameBreak
📵 Screen Detox – Join Screen Break  
🛡️ NoFap Recovery – Join NOFAP
💸 Money Habits & Business Growth – Join MONEY TALK

⚡ Want to start tracking your daily progress, detox streaks, or focus habits? Click the button below or DM me /start to activate your personal tracking assistant today.

Let's transmute distraction into power!

Message me if you need anything else! 💪""",

    "Moneytalk": """👋 Hey @{username}! Welcome to MONEY TALK 💼

This is where we turn cheap dopamine time into income-generating time. Expect convos on freelancing, future trends, biz ideas, and smart money moves.

Want to start building good habits today? Click the button below or dm me /start so I can track your productivity streaks and help you stay consistent. 🚀

Message me if you need anything else! 💪"""
}

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining groups with welcome messages."""
    if not update.message or not update.message.new_chat_members:
        return
    
    chat_id = update.message.chat_id
    
    # Find which group this is
    group_name = None
    for name, group_id in GROUP_CHAT_IDS.items():
        if group_id == chat_id:
            group_name = name
            break
    
    if not group_name:
        return  # Not one of our groups
    
    # Send welcome message for each new member
    for new_member in update.message.new_chat_members:
        # Skip if it's the bot itself
        if new_member.id == context.bot.id:
            continue
        
        # Get username or first name
        username = new_member.username or new_member.first_name or "there"
        first_name = new_member.first_name or "there"
        
        # Get the appropriate welcome message
        welcome_template = WELCOME_MESSAGES.get(group_name)
        if not welcome_template:
            continue
        
        # Format the message
        welcome_message = welcome_template.format(
            username=username,
            first_name=first_name
        )
        
        # Create inline keyboard with start button
        keyboard = [
            [InlineKeyboardButton("🚀 Start My Journey", callback_data="welcome_start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Error sending welcome message: {e}")

async def handle_welcome_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the welcome start button callback."""
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    # Try to send a private message to start the onboarding process
    try:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="🎉 Welcome! Let's get you started on your journey. I'll help you set up your personal tracking and accountability system.\n\nClick /start to begin your onboarding process!"
        )
        # Update the original message to show success
        await query.edit_message_text(
            text=f"✅ Perfect! I've sent you a private message, @{query.from_user.username or query.from_user.first_name}. Check your DMs to continue with the setup! 🚀"
        )
    except Exception as e:
        # If we can't send a private message, provide clear instructions
        await query.edit_message_text(
            text=f"🎉 Welcome @{query.from_user.username or query.from_user.first_name}! To start your journey:\n\n1️⃣ Click on my profile (@dopamine_bot_2024)\n2️⃣ Click 'Start' or 'Send Message'\n3️⃣ Type /start to begin your onboarding\n\nI'll help you set up your personal tracking system! 🚀"
        )

MEDIA_DIR = "user_commitments"
os.makedirs(MEDIA_DIR, exist_ok=True)

# Group prompts database
GROUP_PROMPTS = {
    "General": {
        "text": [
            "🌟 Today's Discussion Topic: Kung hindi ka naging addict sa dopamine... saan napunta ang energy mo ngayon? 🤔",
            "🌟 Today's Discussion Topic: Alin ang mas malala? 5 hours of TikTok or 1 ex na ayaw mong bitawan?",
            "🌟 Today's Discussion Topic: If you could transmute your urges into one superpower, what would it be?",
            "🌟 Today's Discussion Topic: Minsan ba feeling mo parang useless ka pag wala kang cheap dopamine hits?",
            "🌟 Today's Discussion Topic: Ano ang pinaka malupit na craving mo this week?😭",
            "🌟 Today's Discussion Topic: Ano ang reward mo sa sarili mo for going on a dopamine detox?",
            "🌟 Today's Discussion Topic: What was your biggest 'come to Jesus' moment about your addiction?",
            "🌟 Today's Discussion Topic: Kapag tinamaan ka ng craving… anong sinasabi mo sa sarili mo to survive?",
            "🌟 Today's Discussion Topic: What does 'transmutation' actually mean to you? No BS answers.",
            "🌟 Today's Discussion Topic: Pano malalaman kung gusto mo talaga gumaling o gusto mo lang ng validation na 'you're trying'?",
            "🌟 Today's Discussion Topic: What was your first dopamine addiction?",
            "🌟 Today's Discussion Topic: If hindi pa na-aadik yung younger self mo sa dopamine… anong advice mo sa kanya?"
        ],
        "polls": [
            {"question": "What's the hardest dopamine habit to let go of?", "options": ["Scrolling", "Porn", "Junk food", "Gaming", "Overthinking 😅"]},
            {"question": "Be honest. Anong distraction ang pinaka guilty pleasure mo?", "options": ["Reels", "Just one game", "Food trip", "Netflix + chill (solo version 😏)", "Sleep to escape"]},
            {"question": "Anong gusto mong ma-master habang nasa detox ka?", "options": ["Focus", "Discipline", "Creativity", "Business", "Fitness"]},
            {"question": "Which statement hits harder?", "options": ["You let your younger self down.", "Comfort is killing your edge.", "You became what you used to hate.", "You've been escaping life, not living it."]},
            {"question": "What's your current relapse trigger?", "options": ["Boredom", "Loneliness", "Stress", "Nighttime routines", "Wala lang, bigla na lang..."]},
            {"question": "How do you cope without cheap dopamine?", "options": ["Journaling", "Breathwork", "Deep work", "Lifting heavy stuff", "Ka-chat si bot 😅"]},
            {"question": "Pili ka: Your 30-day streak OR 1 full day of binging with no guilt?", "options": ["Streak life", "Cheat day", "Depends on the mood", "Di ko na alam, bro. Haha."]},
            {"question": "Which of these lowkey destroy your discipline the most?", "options": ["Deserve ko naman to eh", "Last na to, promise", "Konti lang, hindi counted", "Nag-progress naman ako kahapon eh"]},
            {"question": "If all your urges turned into power, what would you build?", "options": ["6-pack", "6-figure biz", "Deep, meaningful art", "True peace", "Real relationships"]},
            {"question": "What's your main reason for staying clean?", "options": ["I'm tired of being a slave", "I want my confidence back", "I want to build something real", "I want to be proud of myself"]},
            {"question": "You're on a 100-day streak. What's your reward?", "options": ["A tattoo", "A solo trip", "A massive flex post", "A silent celebration", "A cheat day (oops 😅)"]},
            {"question": "If you had to restart your journey tomorrow, what would you change?", "options": ["Better habits", "Less pressure", "Accountability", "Daily tracking", "Not trying to be perfect"]}
        ]
    },
    "NoFap": {
        "text": [
            "⛔ Today's Discussion Topic: Anong mas mahirap… NoFap o 'di na siya i-chat ulit kahit online siya ngayon?' 😭",
            "⛔ Today's Discussion Topic: Bro to bro: what was your lowest moment during a relapse?",
            "⛔ Today's Discussion Topic: What do you do when your brain screams 'Just this one time'?",
            "⛔ Today's Discussion Topic: Kung makakausap mo ang younger self mo mo bago mag-porn, anong sasabihin mo?",
            "⛔ Today's Discussion Topic: What's one thing NoFap made you realize about yourself that porn had blinded you from?",
            "⛔ Today's Discussion Topic: Let's get raw: ano ang emotional need na tinatago sa likod ng PMO?",
            "⛔ Today's Discussion Topic: Sino mas malakas: yung kaya mag 1000 push-ups or 100 days no fap? 😅",
            "⛔ Today's Discussion Topic: Saan mo gusto mapunta yung extra energy mo?",
            "⛔ Today's Discussion Topic: Kung may 1 mindset switch na nakatulong sa'yo mag-NoFap, ano yun?",
            "⛔ Today's Discussion Topic: Be honest: Anong oras ka pinaka-tempted?",
            "⛔ Today's Discussion Topic: Nagtry ka na ba ng porn blocking apps?",
            "⛔ Today's Discussion Topic: Ano yung pinakamalaking nawala sayo dahil sa porn?"
        ],
        "polls": [
            {"question": "What's your most dangerous trigger right now?", "options": ["Instagram baddies", "TikTok black hole", "Lonely late nights", "Stress", "I don't even know anymore…"]},
            {"question": "Pili ka: 30-day streak with zero urges OR 60-day streak full of temptations?", "options": ["30 chill days", "60 warrior days", "Neither, I already relapsed 😅", "What's a streak? 😭"]},
            {"question": "Biggest lie you tell yourself before a relapse?", "options": ["Just one last time", "This doesn't count", "I'll bounce back tomorrow", "Deserve ko to eh", "All of the above 😭"]},
            {"question": "What's your post-nut clarity usually like?", "options": ["Existential dread", "What am I doing with my life…", "Delete all tabs", "Eat something then cry", "Okay lang yan, next time ulit"]},
            {"question": "Ano ang pinaka-hype mong benefit sa NoFap?", "options": ["More energy", "Better confidence", "Laser focus", "Malakas sa chicks 😅", "I just wanna stop feeling like trash 😭"]},
            {"question": "How long was your longest clean streak ever?", "options": ["1–7 days", "2–3 weeks", "1–2 months", "90+ days", "I stopped counting"]},
            {"question": "If you relapse tonight, what will you do tomorrow?", "options": ["Sulk and self-blame", "Journal and try again", "Quit for good", "Go on another binge", "Call someone and confess"]},
            {"question": "If porn didn't exist, would your life be 10x better?", "options": ["Yes, no question", "Hmm, maybe", "Not really", "I'd just get addicted to something else 😅"]},
            {"question": "Anong pinaka-random na ginawa mo para lang 'di mag-relapse?", "options": ["Took a cold shower", "Did 50 push-ups", "Went for a walk", "Talked to the bot", "Ate cereal at 2AM 😂"]},
            {"question": "NoFap for 1 year = ???", "options": ["Millionaire mindset", "Greek god bod", "Monk mode powers", "Boring but peaceful", "Can't imagine it tbh"]},
            {"question": "What do you believe porn is doing to society?", "options": ["Weakening men", "Killing relationships", "Normalizing loneliness", "Warping sex", "All of the above"]},
            {"question": "Kung may NoFap mascot, ano siya?", "options": ["Warrior monk", "One Punch Man", "Grimace", "Robot na walang feelings", "Saging na hindi binabalat 😂"]}
        ]
    },
    "ScreenBreak": {
        "text": [
            "📵 Today's Discussion Topic: Ilang times ka nag-swipe tapos na-realize mong wala ka naman talagang hinahanap?",
            "📵 Today's Discussion Topic: Ano ang main theme ng 'Explore Page' mo ngayon?🤔",
            "📵 Today's Discussion Topic: What's your go-to excuse every time you open social media 'for just 2 minutes'?",
            "📵 Today's Discussion Topic: Gano katagal yung pinakamatagal mong scroll sa CR🚽?",
            "📵 Today's Discussion Topic: Ano ang pinakarandom topic na napanood mo sa tikok?",
            "📵 Today's Discussion Topic: Kapag sinabi mong 'last video na 'to'… ilang last videos usually yun? 😅",
            "📵 Today's Discussion Topic: Anong mas nakaka-puyat? Pagstalk kay crush sa ig or tiktok scrolling? 🥲",
            "📵 Today's Discussion Topic: 1-week no scroll OR 1-week walang internet? 😈",
            "📵 Today's Discussion Topic: Anong klaseng content ang weakness mo talaga? 'Yung kahit alam mong sayang oras… GO pa rin.💅🐶📉",
            "📵 Today's Discussion Topic: Ano ang pinaka-late na oras mong natulog kaka-scroll?😅",
            "📵 Today's Discussion Topic: May time ba ever na sumama pakiramdam mo kaka-scroll? 🤔",
            "📵 Today's Discussion Topic: On a scale of 1-10, how uncomfortable do you feel pag di ka maka-scroll for 3 days?🤔"
        ],
        "polls": [
            {"question": "Which app traps you the most?", "options": ["TikTok", "YouTube Shorts", "Facebook", "Instagram", "Twitter/X"]},
            {"question": "Biggest lie you tell yourself before doomscrolling?", "options": ["Just 5 minutes", "I'm just checking something", "I deserve a break", "At least di ako nag-p*rn", "All of the above 😅"]},
            {"question": "Most dangerous time to scroll?", "options": ["Before bed", "Right after waking up", "When bored", "While pooping", "During work (oops 😬)"]},
            {"question": "If you removed 1 app today, which would give you the most peace?", "options": ["TikTok", "Instagram", "YouTube", "Facebook", "Netflix"]},
            {"question": "Anong klaseng content ang pinaka-hirap tigilan?", "options": ["Conspiracy theories", "Chismis & drama", "Motivational na di mo sinusunod", "Toxic news", "Meme compilations"]},
            {"question": "Have you ever doomscrolled until your hand hurt or your eyes stung?", "options": ["Yes, almost daily", "Minsan", "Once or twice", "Nope, never", "Hindi ko na maalala 😭"]},
            {"question": "If you had to replace scrolling with 1 activity, anong papalit?", "options": ["Reading a real book", "Starting a biz", "Journaling or self-reflection", "Talking to real people", "Working out"]},
            {"question": "What's the sneakiest form of digital self-sabotage?", "options": ["Watching educational videos na di mo ina-apply", "Comparing lives via stories", "Endless scrolling without learning", "Reading 10 productivity tips but doing 0"]},
            {"question": "What's your average daily screen time?", "options": ["Under 2 hours", "2–4 hours", "4–6 hours", "6–8 hours", "Don't wanna say 🫣"]},
            {"question": "Pili ka: Delete social media for 30 days OR post a tiktok video of you dancing publicly?", "options": ["Bye social media", "I'll dance it out 😆", "Can I delete myself instead?", "Di ko kaya, bro."]},
            {"question": "What do you think is the deeper reason behind your scrolling habit?", "options": ["Escaping boredom", "Escaping anxiety", "Escaping loneliness", "Escaping responsibility", "Escaping reality"]},
            {"question": "Kapag nawala lahat ng short-form content sa mundo bukas, anong gagawin mo?", "options": ["Build something real", "Cry inside", "Read again", "Finally breathe", "Other"]}
        ]
    },
    "GameBreak": {
        "text": [
            "🎮 Today's Discussion Topic: Let's be honest — ilang beses ka na ba naglaro 'for 1 game lang' tapos 5 hours later… 🎮⏳",
            "🎮 Today's Discussion Topic: If you took life as seriously as your games, do you think you would be successful?",
            "🎮 Today's Discussion Topic: Anong mas sakit? Matalo sa high rank game o mapagalitan ni boss?😬",
            "🎮 Today's Discussion Topic: Magkano na ang pinakamalaking nagastos mo sa battle pass o skins🤔?",
            "🎮 Today's Discussion Topic: Kung hindi nag-eexist ang gaming, saan kaya napunta ang oras mo?🤔",
            "🎮 Today's Discussion Topic: Anong mas nakakainis? 10-game losing streak or kinagat ka ng aso?🤔",
            "🎮 Today's Discussion Topic: Kung may trophy yung 'pinaka-walang tulog dahil sa laro'… ilang oras entry mo? 🏆",
            "🎮 Today's Discussion Topic: Nagkaroon ka na ba ever ng 'I need to uninstall this game' moment? 😵‍💫",
            "🎮 Today's Discussion Topic: You ever rage quit tapos sinabi mong 'di na ko maglalaro ulit'… tapos 3 hours later nag-login ka ulit? 😅",
            "🎮 Today's Discussion Topic: Ano mas nakakahiya: herald ka pa rin after 1 year, or nalugi negosyo mo? 💼",
            "🎮 Today's Discussion Topic: Alin ang pinaka mahirap sa journey mo: boredom, cravings, or finding purpose?",
            "🎮 Today's Discussion Topic: Kung may skill tree IRL, anong first upgrade na Gagarin mo? (e.g. self-control, finances, swag) 🧠"
        ],
        "polls": [
            {"question": "What's your ultimate gaming red flag?", "options": ["One last game at 3AM", "Rage quits sa ML / COD", "Canceled plans to grind", "Skipped meals para lang maglaro", "Na-scam sa gacha 😭"]},
            {"question": "If gaming didn't exist, anong most likely addiction mo?", "options": ["Doomscrolling", "YouTube rabbit holes", "Hustle culture", "Overthinking", "Wala… I'd be a monk na 🤣"]},
            {"question": "Anong klaseng gamer ka dati?", "options": ["E-sports player", "Rank grinder", "Noob na trash talker", "AFK / Feeder aminin mo 😅"]},
            {"question": "Most common excuse for overgaming?", "options": ["Relaxation lang to", "Deserve ko 'to", "Nasa bahay lang naman ako", "At least di ako naglalasing"]},
            {"question": "Kapag tilt na tilt ka in-game, what do you usually do?", "options": ["Play more", "Rage quit", "Trash talk sa GC", "Reflect and uninstall (for 1 day 😅)"]},
            {"question": "What's your real-life version of leveling up today?", "options": ["Working out", "Building a biz", "Reading 10 pages", "Talking to actual people", "Sleeping on time 😭"]},
            {"question": "Ano ang pinaka nakakahiya mong gaming addiction moment?", "options": ["Umiyak sa loss", "Sinigawan parents", "Forgot deadline", "Ignored jowa call", "Lahat 😭"]},
            {"question": "Most addicting part of gaming?", "options": ["Winning", "Social bonding", "Escaping life", "Controlling virtual player", "Collecting skins"]},
            {"question": "Pinaka-malupit na gamer excuse ever?", "options": ["Isa pa then sleep", "At least di ako lumalabas", "Mental health break daw sabi sa TikTok", "Basta masaya ako, okay na yun"]},
            {"question": "What's the game you've played the most?", "options": ["Mobile Legends", "Valorant / CS", "Genshin Impact", "DOTA 2", "Minecraft / Roblox"]},
            {"question": "Real talk: What's gaming covering up for you right now?", "options": ["Loneliness", "Career confusion", "Family pressure", "Boredom", "Mental exhaustion"]},
            {"question": "What's your preferred 'productive transmutation' while off games?", "options": ["Workout", "Learn a skill", "Start a hustle", "Write / create content", "Try not to open Steam 😭"]}
        ]
    },
    "Moneytalk": {
        "text": [
            "💰 Today's Discussion Topic: If you were given ₱100K today but bawal mo siya i-save — anong gagawin mo? 💸",
            "💰 Today's Discussion Topic: Ano mas madali? magka-jowa or magka-consistent cashflow? 😅",
            "💰 Today's Discussion Topic: Anong biggest lie na napaniwalaan mo about success or money? 🤔",
            "💰 Today's Discussion Topic: Kung bibigyan ka ng ₱1M today pero you can't work for 1 whole year… tatanggapin mo? 😬",
            "💰 Today's Discussion Topic: If you opened a start-up in year 2050, what product or service would you offer? 🚀",
            "💰 Today's Discussion Topic: If AI took over your job today, what skill would you start learning immediately? 🤖",
            "💰 Today's Discussion Topic: Real talk: What's one toxic money belief you inherited from your family? 🧠",
            "💰 Today's Discussion Topic: Anong pinaka-proud ka na ginawa mo para sa financial future mo — kahit walang nakakakita? 🙌",
            "💰 Today's Discussion Topic: Kung pwede kang mag-reset ng career right now with no risk, anong path pipiliin mo?",
            "💰 Today's Discussion Topic: If the internet disappeared today, do you think your business/income/job would survive?",
            "💰 Today's Discussion Topic: Do you really need more knowledge or just more action right now?",
            "💰 Today's Discussion Topic: Ano mas importante for success: skill, discipline, or connections?"
        ],
        "polls": [
            {"question": "What's your delulu money fantasy?", "options": ["Mag-viral bigla and get rich", "A stranger invests in me", "Lotto win", "Matutulog lang then gising na may ₱M", "Magka-sugar mommy/daddy 🫣"]},
            {"question": "Most tempting 'productivity killer' lately?", "options": ["Doomscrolling", "Netflix binge", "TikTok every 5 mins", "Random YouTube rabbit holes", "Overplanning but underdoing 😵‍💫"]},
            {"question": "Biggest block to building wealth?", "options": ["Poor money habits", "No mentor", "Fear of selling", "Lack of consistency", "Overthinking everything"]},
            {"question": "Kung may free course ka today, what would you choose?", "options": ["Copywriting for $$$", "Stock trading", "Building an AI biz", "Personal branding", "Crypto masterclass"]},
            {"question": "Most delusional spending excuse mo?", "options": ["Investment naman 'to", "Deserve ko 'to", "Last na talaga promise", "Future me will figure it out"]},
            {"question": "How do you define real freedom?", "options": ["Time freedom", "Creative freedom", "Financial independence", "Location freedom", "Mental peace"]},
            {"question": "Pinaka-underrated skill sa 2025?", "options": ["Automation", "High-ticket sales", "AI prompting", "Emotional regulation", "Clear communication"]},
            {"question": "What's your current money move?", "options": ["Investing in self", "Building new income stream", "Cleaning finances", "Stacking savings", "Winging it every day 😅"]},
            {"question": "Anong ginagawa mo pag may bagong idea ka?", "options": ["Hype na hype", "Plan agad", "Launch agad kahit kulang", "Nilista lang muna tapos tinutulugan"]},
            {"question": "Your ideal 'productive escape' kapag burnout na?", "options": ["Nature trip", "Deep work retreat", "Journaling detox", "Silent Airbnb lang", "Uwi sa probinsya to recharge"]},
            {"question": "Biggest reason you're still not rich?", "options": ["No clear goal", "Too scared to sell", "Kalaban sarili", "Procrastination overload", "All of the above 😅"]},
            {"question": "What keeps you going pag gusto mo na sumuko?", "options": ["Future dream life", "Wala nang choice", "People who believe in me", "My past self who fought hard", "Pet ko 😭"]}
        ]
    }
}

# Group prompt tracking - store current prompt index for each group
GROUP_PROMPT_INDEX = {
    "General": 0,
    "NoFap": 0,
    "ScreenBreak": 0,
    "GameBreak": 0,
    "Moneytalk": 0
}

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
    print(f"[DEBUG] get_chatgpt_response called with question: {user_question} and context: {user_context}")
    if not OPENAI_API_KEY:
        print("[DEBUG] OPENAI_API_KEY not set")
        return "I'm sorry, I'm not able to provide personalized advice right now. Please try again later."
    try:
        # Build context-aware prompt
        habit_target = user_context.get('fasting_target', 'their habit')
        current_streak = user_context.get('current_streak', 0)
        group = user_context.get('group', 'None')
        system_prompt = f"""You are a supportive friend and accountability partner helping with habit transformation. Be warm, conversational, and personal - like talking to a friend, not reading from a textbook. You have deep knowledge of neuroscience, psychology, and consciousness.

User Context:
- They are trying to break the habit of: {habit_target}
- Current streak: {current_streak} days
- Accountability group: {group}

Guidelines:
- Talk like a real person having a conversation, not a chatbot
- Give specific, actionable advice tailored to their situation
- Use their name or refer to their specific habit when possible
- Be encouraging and celebrate their progress
- Only end conversations when the user explicitly says goodbye, thanks, or indicates they're done
- If the user asks something outside of habit change, motivation, or wellness, admit it's outside your expertise and do NOT try to answer
- Avoid generic lists and bullet points unless specifically asked
- Use natural language and conversational tone
- Focus on helping with their specific habit: {habit_target}
- Be conversational and engaging - ask follow-up questions when appropriate
- NEVER share personal stories, experiences, or anecdotes about yourself
- NEVER pretend to have personal experiences or memories
- Use general examples and research-based insights instead of personal stories
- Ask follow-up questions to keep the conversation flowing
- AVOID repetitive greetings like "Hey there!", "Hello!", or "Hi!" - jump straight into the conversation
- Vary your conversation starters - don't use the same greeting patterns repeatedly
- Be natural and authentic in your responses

Deep Knowledge Areas (use when relevant):
🧠 **Dopamine Neuroscience**: Explain how dopamine works, reward pathways, tolerance, and how to reset your brain's reward system
🎯 **Purpose & Meaning**: Help users connect their habit change to deeper purpose, values, and life vision
🌑 **Shadow Work**: Guide users to explore the unconscious patterns, fears, and wounds driving their habits
⚡ **Energy & Desire Transmutation**: Teach how to redirect addictive energy into creative, productive, and spiritual pursuits
🧘 **Awareness & Mindfulness**: Help develop present-moment awareness and conscious choice-making
🔄 **Subconscious Reprogramming**: Explain how to rewire neural pathways and change limiting beliefs
😌 **Parasympathetic vs Sympathetic**: Teach nervous system regulation and stress management
💫 **Consciousness & Higher Self**: Guide users toward their authentic self beyond ego and conditioning

Response Style Examples:
❌ DON'T: "Hey there! When I was trying to quit [habit], I found that..." (fictional personal story + repetitive greeting)
❌ DON'T: "Hello! I remember when I used to..." (fictional personal memory + repetitive greeting)
✅ DO: "Your brain has literally rewired itself around [habit]. Every time you do it, you're strengthening neural pathways that make it harder to resist next time. But here's the thing - your brain is also plastic. Every time you choose NOT to [habit], you're weakening those pathways and building new ones. What's one situation where you can practice this rewiring today?"

❌ DON'T: "Hey there! I've found that starting super small works best..." (fictional personal experience + repetitive greeting)
✅ DO: "Your nervous system is constantly scanning for threats and rewards. When you're stressed (sympathetic mode), your brain craves quick dopamine hits. But when you're in parasympathetic mode - calm, centered, present - you can make conscious choices instead of reacting. What's one way you can activate your parasympathetic nervous system before making a choice about [habit]?"

❌ DON'T: "Here are 5 steps to create better habits: 1. Identify triggers 2. Set goals 3. Track progress..."
✅ DO: "Behind every habit is a shadow - an unconscious pattern, fear, or wound you're trying to soothe. Your [habit] isn't just about the behavior; it's about what you're running from or trying to fill. What emotion or situation usually triggers your [habit]? That's where the real work begins."

Deep Insights to Share:
- "Your dopamine system is like a muscle - the more you use it for cheap hits, the weaker it gets for real rewards"
- "Every urge is energy that can be transmuted. That craving for [habit]? That's pure creative energy waiting to be redirected"
- "Your subconscious mind runs 95% of your behavior. The key isn't willpower - it's reprogramming the deeper patterns"
- "Stress puts you in fight-or-flight mode, making you crave quick dopamine. Calm puts you in rest-and-digest mode, where conscious choice is possible"
- "Your shadow - the parts of yourself you reject - often drives your most destructive habits. Integration, not suppression, is the path"
- "Awareness is the first step. When you can observe your urges without acting on them, you're no longer a slave to them"
- "Purpose is the ultimate dopamine hack. When you're connected to something bigger than yourself, cheap dopamine loses its power"
"""
        greetings = ["hi", "hello", "kamusta", "hey", "yo", "sup", "kumusta", "good morning", "good afternoon", "good evening"]
        closing_phrases = ["thanks", "thank you", "ty", "thx", "that's all", "im good", "i'm good", "bye", "see you", "talk later", "done", "no more", "that's it", "alright"]
        user_message = user_question.strip().lower()
        
        # Only end conversation if user explicitly uses closing phrases
        # Don't end just because message is short
        if any(phrase in user_message for phrase in closing_phrases):
            return "👍 No problem! If you need anything else, just message me anytime. Have a great day!"
        
        # Dynamic response length
        if len(user_message.split()) <= 4 or any(greet in user_message for greet in greetings):
            max_tokens = 120  # Short, friendly reply
        else:
            max_tokens = min(500, max(120, len(user_message.split()) * 4))  # More conversational responses
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        print(f"[DEBUG] Sending request to OpenAI API with max_tokens={max_tokens}...")
        def do_openai_call():
            return client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_question}
                ],
                max_tokens=max_tokens,
                temperature=0.7
            )
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(do_openai_call),
                timeout=10  # seconds
            )
        except asyncio.TimeoutError:
            print("[ERROR] ChatGPT API timed out")
            return "I'm having trouble connecting to my advice system right now (timeout). Try asking me again in a moment!"
        print("[DEBUG] Received response from OpenAI API")
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
                elif entry.get("status") == "reset":
                    # Stop counting when we hit a reset (user stopped and resumed)
                    break
                else:
                    # Stop counting on any "no" or other status
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
        user_row = None
        for i, row in enumerate(rows):
            if str(row.get('user_id', '')) == user_id:
                user_row = row
                break
        if user_row:
            # User exists, offer choice
            await update.message.reply_text(
                "You already have an active habit and check-in setup. Would you like to go through onboarding again (to set a new habit, group, etc.), or just resume daily check-ins?",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 Start Over", callback_data="onboarding_restart"),
                        InlineKeyboardButton("✅ Resume Check-ins", callback_data="onboarding_resume")
                    ]
                ])
            )
            return
        # New user: start onboarding
        context.user_data['onboarding_state'] = 'habit'
        await update.message.reply_text(
            "👋 Welcome to your habit transformation journey!\n\n"
            "I'm here to help you build better habits and break the ones that aren't serving you.\n\n"
            "🎯 What bad habit are you most excited to take a break from right now?\n\n"
            "Some popular examples:\n"
            "• 🎮 Gaming\n"
            "• 📱 Social media (TikTok, Instagram, etc.)\n"
            "• 🍬 Sugar/junk food\n"
            "• 🚬 Smoking\n"
            "• 🍺 Alcohol\n"
            "• 📱 Mindless scrolling\n\n"
            "Tell me what you'd like to work on by typing it below!"
        )
    except Exception as e:
        print(f"[ERROR] Error in start: {e}")
        if update.message:
            await update.message.reply_text("There was an error starting onboarding. Please try again.")

async def handle_onboarding_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    query = update.callback_query
    if not query or not hasattr(query, 'data'):
        return
    await query.answer()
    if query.data == "onboarding_restart":
        # Clear all old onboarding data to start fresh
        context.user_data.clear()
        context.user_data['onboarding_state'] = 'habit'
        
        # Add a "reset" entry to break the streak when they restart
        user_id = str(query.from_user.id)
        timestamp = get_pht_timestamp()
        try:
            checkin_sheet = gc.open_by_key(SHEET_ID).worksheet("Daily Check-ins")
        except Exception as e:
            checkin_sheet = gc.open_by_key(SHEET_ID).add_worksheet(title="Daily Check-ins", rows=1000, cols=5)
            checkin_sheet.append_row(["user_id", "status", "timestamp"])
        checkin_sheet.append_row([user_id, "reset", timestamp])
        print(f"[DEBUG] Added reset entry for user {user_id} when they restarted onboarding")
        print(f"[DEBUG] Cleared all old onboarding data for user {user_id}")
        
        if query.message and hasattr(query.message, 'reply_text'):
            await query.message.reply_text(
                "🔄 Let's start fresh! What habit do you want to fast from or break? (e.g. alcohol, gaming, social media, etc.)"
            )
    elif query.data == "onboarding_resume":
        # Set user as active and send confirmation
        user_id = str(query.from_user.id)
        rows = worksheet.get_all_records()
        for i, row in enumerate(rows):
            if str(row.get('user_id', '')) == user_id:
                worksheet.update_cell(i + 2, SHEET_COLUMNS['STATUS'], "active")
                break
        if query.message and hasattr(query.message, 'reply_text'):
            await query.message.reply_text("✅ You're all set! I'll resume your daily check-ins. If you want to change your habit or group, just type /start again.")

def user_wants_to_pause(text):
    """Detect if the user wants to pause or end the conversation."""
    if not text:
        return False
    text = text.lower().strip()
    
    # Only detect explicit pause/stop requests
    PAUSE_PHRASES = [
        # Direct stop/pause requests
        "stop", "pause", "end", "quit", "exit",
        "i'm done", "im done", "i'm finished", "im finished",
        "that's it", "thats it", "that's all", "thats all",
        "no more", "enough", "i'm good", "im good",
        "i'm fine", "im fine", "i'm satisfied", "im satisfied",
        "i'm complete", "im complete",
        
        # Polite ways to end conversation
        "thanks", "thank you", "ty", "thx",
        "thanks anyway", "thank you anyway",
        "thanks but", "thank you but",
        "i'll let you know", "i will let you know",
        "i'll reach out", "i will reach out",
        "i'll message", "i will message",
        "i'll contact", "i will contact",
        "i'll get in touch", "i will get in touch",
        
        # Time-based endings
        "for now", "for today", "for today",
        "right now", "at the moment", "currently",
        "i'm busy", "im busy", "i'm occupied", "im occupied",
        "i have to go", "i need to go", "i gotta go",
        "i need to leave", "i have to leave",
        
        # Dismissive responses
        "whatever", "nevermind", "never mind",
        "don't worry", "dont worry", "no worries",
        "it's nothing", "its nothing", "not important",
        
        # Specific to this bot context
        "i don't need help", "i dont need help",
        "i don't need support", "i dont need support",
        "i don't need advice", "i dont need advice",
        "i don't want to talk", "i dont want to talk",
        "i don't feel like talking", "i dont feel like talking",
        "i'm not in the mood", "im not in the mood",
        
        # Filipino/Tagalog phrases
        "sige", "sige na", "tama na",
        "ayos na", "pwede na", "tama na yan",
        "salamat", "salamat na lang", "thank you na lang",
        "ayaw ko na", "tamad na ako", "pagod na ako",
        
        # Emoji-only responses
        "👍", "👌", "✌️", "🤙", "👋", "🙏"
    ]
    
    # Check for exact matches first
    for phrase in PAUSE_PHRASES:
        if text == phrase:
            return True
    
    # Check for phrases within the text (only longer phrases)
    for phrase in PAUSE_PHRASES:
        if phrase in text and len(phrase) > 3:  # Only check longer phrases
            return True
    
    return False

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[DEBUG] ===== handle_message called =====")
    print("[DEBUG] Update type:", type(update))
    print("[DEBUG] Has message:", hasattr(update, 'message') and update.message is not None)
    print("[DEBUG] Has callback_query:", hasattr(update, 'callback_query') and update.callback_query is not None)
    if hasattr(update, 'message') and update.message:
        print("[DEBUG] Message text:", getattr(update.message, 'text', 'No text'))
    if hasattr(update, 'callback_query') and update.callback_query:
        print("[DEBUG] Callback data:", getattr(update.callback_query, 'data', 'No data'))
    
    print("[DEBUG] handle_message called, context.user_data:", getattr(context, 'user_data', None))
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    
    onboarding_state = context.user_data.get('onboarding_state')
    print(f"[DEBUG] Current onboarding_state: {onboarding_state}")
    
    # --- Onboarding: Baseline Q&A Permission ---
    if onboarding_state == 'baseline_permission':
        print("[DEBUG] In baseline_permission state")
        if update.callback_query and update.callback_query.data:
            data = update.callback_query.data
            await update.callback_query.answer()
            if data == 'baseline_permission_yes':
                context.user_data['onboarding_baseline_permission'] = 'yes'
                await ask_onboarding_baseline(update, context)
            else:
                context.user_data['onboarding_baseline_permission'] = 'no'
                await finalize_onboarding(update, context)
        else:
            if update.message and hasattr(update.message, 'reply_text'):
                await update.message.reply_text("Please use the buttons to answer: Is it okay if I ask you a few questions?")
        return
    # --- Onboarding: Baseline Q&A ---
    if onboarding_state == 'baseline':
        print("[DEBUG] In baseline state")
        baseline_questions = context.user_data.get('onboarding_baseline_questions', []) or []
        q_idx = context.user_data.get('onboarding_baseline_q_idx', 0)
        if q_idx < len(baseline_questions):
            q_type = baseline_questions[q_idx]['type'] if q_idx < len(baseline_questions) else None
            # Handle scale answers via callback_query
            if q_type == 'scale' and update.callback_query and update.callback_query.data and update.callback_query.data.startswith('onboarding_scale_'):
                answer = update.callback_query.data.split('_')[-1]
                print(f"[DEBUG] Processing scale answer: {answer} for q_idx={q_idx}, q_type={q_type}")
                await update.callback_query.answer()
                try:
                    await update.callback_query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    pass
                context.user_data['onboarding_baseline_answers'] = context.user_data.get('onboarding_baseline_answers', [])
                context.user_data['onboarding_baseline_answers'].append(answer)
                context.user_data['onboarding_baseline_q_idx'] = q_idx + 1
                print(f"[DEBUG] Updated q_idx from {q_idx} to {q_idx + 1}")
                
                # Send acknowledgment based on question type
                if q_idx == 0:  # Focus question
                    print(f"[DEBUG] Sending focus acknowledgment for q_idx={q_idx}")
                    if update.effective_chat:
                        await update.effective_chat.send_message("🧠 Noted! Your focus level is recorded.")
                elif q_idx == 1:  # Impulse control question
                    print(f"[DEBUG] Sending impulse control acknowledgment for q_idx={q_idx}")
                    if update.effective_chat:
                        await update.effective_chat.send_message("💪 Got it! Your self-control baseline is set.")
                
                # Send next question
                if q_idx + 1 < len(baseline_questions):
                    next_q = baseline_questions[q_idx + 1]['q']
                    next_type = baseline_questions[q_idx + 1]['type']
                    if next_type == 'scale':
                        reply_markup = InlineKeyboardMarkup([
                            [InlineKeyboardButton(str(i), callback_data=f"onboarding_scale_{i}") for i in range(1, 6)]
                        ])
                        if update.effective_chat:
                            await update.effective_chat.send_message(next_q, reply_markup=reply_markup)
                    elif next_type == 'permission':
                        reply_markup = InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Yes", callback_data="onboarding_permission_yes"), InlineKeyboardButton("❌ No", callback_data="onboarding_permission_no")]
                        ])
                        if update.effective_chat:
                            await update.effective_chat.send_message(next_q, reply_markup=reply_markup)
                    else:
                        if update.effective_chat:
                            await update.effective_chat.send_message(next_q)
                else:
                    # Should not reach here, but just in case
                    if update.effective_chat:
                        await update.effective_chat.send_message("🙏 Thank you for your feedback! Your answers help us improve and inspire others. 💡✨")
                        await update.effective_chat.send_message("Give me a few seconds to initialize and begin...")
                    await finalize_onboarding(update, context)
                return
            # Handle number/text answer for number question
            elif q_type == 'number' and update.message and update.message.text:
                answer = update.message.text.strip()
                context.user_data['onboarding_baseline_answers'] = context.user_data.get('onboarding_baseline_answers', [])
                context.user_data['onboarding_baseline_answers'].append(answer)
                context.user_data['onboarding_baseline_q_idx'] = q_idx + 1
                
                # Send acknowledgment for number question
                if q_idx == 2:  # Hours spent on habit question
                    if update.effective_chat:
                        await update.effective_chat.send_message("⏰ Noted! Your habit time baseline is recorded.")
                
                if q_idx + 1 < len(baseline_questions):
                    next_q = baseline_questions[q_idx + 1]['q']
                    next_type = baseline_questions[q_idx + 1]['type']
                    if next_type == 'scale':
                        reply_markup = InlineKeyboardMarkup([
                            [InlineKeyboardButton(str(i), callback_data=f"onboarding_scale_{i}") for i in range(1, 6)]
                        ])
                        if update.effective_chat:
                            await update.effective_chat.send_message(next_q, reply_markup=reply_markup)
                    elif next_type == 'permission':
                        reply_markup = InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Yes", callback_data="onboarding_permission_yes"), InlineKeyboardButton("❌ No", callback_data="onboarding_permission_no")]
                        ])
                        if update.effective_chat:
                            await update.effective_chat.send_message(next_q, reply_markup=reply_markup)
                    else:
                        if update.effective_chat:
                            await update.effective_chat.send_message(next_q)
                else:
                    # Should not reach here, but just in case
                    if update.effective_chat:
                        await update.effective_chat.send_message("🙏 Thank you for your feedback! Your answers help us improve and inspire others. 💡✨")
                        await update.effective_chat.send_message("Give me a few seconds to initialize and begin...")
                    await finalize_onboarding(update, context)
                return
            # Handle permission answer via callback_query
            elif q_type == 'permission' and update.callback_query and update.callback_query.data and update.callback_query.data.startswith('onboarding_permission_'):
                answer = 'Yes' if update.callback_query.data == 'onboarding_permission_yes' else 'No'
                await update.callback_query.answer()
                try:
                    await update.callback_query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    pass
                context.user_data['onboarding_baseline_answers'] = context.user_data.get('onboarding_baseline_answers', [])
                context.user_data['onboarding_baseline_answers'].append(answer)
                context.user_data['onboarding_baseline_q_idx'] = q_idx + 1
                # After permission, give appropriate response based on their choice
                if update.effective_chat:
                    if answer == 'Yes':
                        await update.effective_chat.send_message("🙏 Thank you for your feedback! Your answers help us improve and inspire others. 💡✨")
                    else:
                        await update.effective_chat.send_message("👍 No problem! We'll keep your data private and only use it for your personal tracking.")
                    await update.effective_chat.send_message("Give me a few seconds to initialize and begin...")
                await finalize_onboarding(update, context)
                return
            # Fallback for missing/invalid input
            elif q_type == 'number' and (not update.message or not update.message.text):
                if update.effective_chat:
                    await update.effective_chat.send_message("❓ Please reply with a number answer.")
                return
            # If not handled above, ignore
            return
        else:
            if update.message and hasattr(update.message, 'reply_text'):
                await update.message.reply_text("❓ Please reply with your answer.")
        return
    
    # --- Onboarding: capture fasting target ---
    if onboarding_state == 'habit':
        print("[DEBUG] In onboarding (habit) step")
        if not update.message or not hasattr(update.message, 'text') or not update.message.text:
            if update.message and hasattr(update.message, 'reply_text'):
                await update.message.reply_text("❓ Please tell me what habit you want to fast from.")
            return
        habit_input = sanitize_input(update.message.text)
        print(f"[DEBUG] Raw input: {update.message.text}, Sanitized: {habit_input}")
        if not habit_input:
            if update.message and hasattr(update.message, 'reply_text'):
                await update.message.reply_text(ERROR_MESSAGES['INVALID_INPUT'])
            return
        context.user_data["fasting_target"] = habit_input
        context.user_data['onboarding_state'] = 'reminder_consent'
        print(f"[DEBUG] Proceeding to reminder consent step with habit: {habit_input}")
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
        return
    
    # --- General conversation ---
    print("[DEBUG] Not in onboarding (habit), processing as general message")
    if not update.message or not update.message.text:
        print("[DEBUG] No message or text in update")
        return
    if update.message.text.startswith('/'):
        print("[DEBUG] Message is a command, skipping")
        return
    if not update.effective_user:
        print("[DEBUG] No effective user in update")
        return
    
    user_id = str(update.effective_user.id)
    user_text = update.message.text
    
    # Check for pause/stop intent
    if user_wants_to_pause(user_text):
        # Set conversation state to paused
        context.user_data['conversation_paused'] = True
        context.user_data['pause_timestamp'] = get_pht_timestamp()
        
        if update.message and hasattr(update.message, 'reply_text'):
            await update.message.reply_text("Of course! I'm here whenever you need me. Just send a message if you want to talk or need support. 👍")
        return
    
    # Check if conversation was recently paused and user is trying to continue
    if context.user_data.get('conversation_paused'):
        # Clear the pause state and continue normally
        context.user_data.pop('conversation_paused', None)
        context.user_data.pop('pause_timestamp', None)
    
    try:
        rows = worksheet.get_all_records()
        user_data = None
        for row in rows:
            if str(row.get('user_id', '')) == user_id:
                user_data = row
                break
        if not user_data:
            print("[DEBUG] User not found in system, using default context")
            user_context = {
                'fasting_target': 'Unknown',
                'current_streak': 0,
                'group': 'None'
            }
        else:
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
                elif entry.get("status") == "reset":
                    # Stop counting when we hit a reset (user stopped and resumed)
                    break
                else:
                    # Stop counting on any "no" or other status
                    break
            user_context = {
                'fasting_target': user_data.get('fasting_target', 'Unknown'),
                'current_streak': current_streak,
                'group': user_data.get('group', 'None')
            }
        print(f"[DEBUG] Received message: {update.message.text}")
        if update.effective_chat:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        response = await get_chatgpt_response(update.message.text, user_context)
        print(f"[DEBUG] Replying to user with: {response}")
        await update.message.reply_text(response)
    except Exception as e:
        print(f"[ERROR] Error in handle_message: {e}")
        if update.message:
            await update.message.reply_text("I'm having trouble processing your message right now. Please try again later.")

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
            print(f"[DEBUG] User {user_id} responded 'no', checking for 3-day reminder logic")
            # Get all check-ins for this user, most recent first
            try:
                history = checkin_sheet.get_all_records()
            except Exception as e:
                history = []
            user_history = [r for r in reversed(history) if str(r.get("user_id", "")) == str(user_id)]
            print(f"[DEBUG] User {user_id} has {len(user_history)} total check-ins")
            
            # Check if user has at least one 'yes' check-in
            has_yes_checkin = any(r.get("status") == "yes" for r in user_history)
            print(f"[DEBUG] User {user_id} has_yes_checkin: {has_yes_checkin}")
            
            # Get the last 3 check-ins (most recent first)
            last_3 = [r.get("status", "") for r in user_history[:3]]
            print(f"[DEBUG] After 'no' check-in - User {user_id} last_3: {last_3}")
            
            # Get user's reminder settings
            all_rows = worksheet.get_all_records()
            user_row = next((r for r in all_rows if str(r.get('user_id', '')) == str(user_id)), None)
            reminder_sent = user_row.get("reminder_sent", "") if user_row else ""
            media_id = str(user_row.get("media_id", "")) if user_row else ""
            media_type = user_row.get("media_type", "video") if user_row else "video"
            
            print(f"[DEBUG] User {user_id} reminder_sent: '{reminder_sent}', media_id: '{media_id}', media_type: '{media_type}'")
            
            # Check each condition separately
            condition1 = len(last_3) == 3  # Must have exactly 3 check-ins
            condition2 = last_3 == ["no", "no", "no"]  # Last 3 must all be "no"
            condition3 = reminder_sent != "yes"  # Haven't already sent a reminder for this streak
            condition4 = media_id and media_id != ""  # User must have uploaded a media file
            condition5 = media_type in ["voice", "video_note", "audio", "document", "video"]  # Media type must be valid
            
            print(f"[DEBUG] Reminder conditions for user {user_id}:")
            print(f"  - len(last_3) == 3: {condition1}")
            print(f"  - last_3 == ['no', 'no', 'no']: {condition2}")
            print(f"  - reminder_sent != 'yes': {condition3}")
            print(f"  - media_id exists: {condition4}")
            print(f"  - media_type valid: {condition5}")
            
            # Send reminder if this was the 3rd 'no' in a row
            if (condition1 and condition2 and condition3 and condition4 and condition5):
                print(f"[DEBUG] ALL CONDITIONS MET - Sending immediate reminder to user {user_id} after 3rd 'no'")
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
            else:
                print(f"[DEBUG] NOT all conditions met - skipping reminder for user {user_id}")
        
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
                elif entry.get("status") == "reset":
                    # Stop counting when we hit a reset (user stopped and resumed)
                    break
                else:
                    # Stop counting on any "no" or other status
                    break
            print(f"[DEBUG] User {user_id} has a streak of {streak} days")
            milestones = [3, 7, 14, 30, 60, 90]
            if streak in milestones:
                # Check if user has already been asked about this milestone
                user_row = next((r for r in all_rows if str(r.get('user_id', '')) == str(user_id)), None)
                shared_milestones = str(user_row.get("shared_milestones", "")) if user_row else ""
                shared_list = shared_milestones.split(",") if shared_milestones else []
                shared_list = [int(x.strip()) for x in shared_list if x.strip().isdigit()]
                group = str(user_row.get("group", "None")) if user_row else "None"
                print(f"[DEBUG] Milestone share check: group={group}, shared_list={shared_list}, streak={streak}, user_id={user_id}")
                if streak not in shared_list:
                    print(f"[DEBUG] User {user_id} hit milestone {streak} for the first time!")
                    # Find user's group and username
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
                        return  # Don't continue with the rest of the function after feedback trigger
                # Send share prompt if user is in a group
                try:
                    share_markup = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("Share in Group", callback_data=f"streak_share_{group}_{streak}"),
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
                # --- Milestone feedback logic ---
                if streak in MILESTONE_QUESTIONS:
                    # Check if user has already completed feedback for this milestone
                    feedback_completed = ""
                    if user_row:
                        feedback_completed = str(user_row.get("feedback_completed", ""))
                    completed_list = feedback_completed.split(",") if feedback_completed else []
                    completed_list = [int(x.strip()) for x in completed_list if x.strip().isdigit()]
                    
                    print(f"[DEBUG] Milestone feedback check: streak={streak}, completed_list={completed_list}, user_id={user_id}")
                    print(f"[DEBUG] Available milestones: {list(MILESTONE_QUESTIONS.keys())}")
                    
                    if streak not in completed_list:
                        print(f"[DEBUG] User {user_id} has NOT completed feedback for milestone {streak}, starting feedback questions")
                        if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
                            context.user_data = {}
                        context.user_data['pending_feedback'] = {
                            'milestone': streak,
                            'q_idx': 0,
                            'user_id': user_id,
                            'username': username,
                            'answers': []
                        }
                        await send_next_feedback_question(update, context)
                    else:
                        print(f"[DEBUG] User {user_id} has already completed feedback for milestone {streak}, skipping questions")
        
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
                
                # Add a "reset" entry to break the streak when they resume
                timestamp = get_pht_timestamp()
                try:
                    checkin_sheet = gc.open_by_key(SHEET_ID).worksheet("Daily Check-ins")
                except Exception as e:
                    checkin_sheet = gc.open_by_key(SHEET_ID).add_worksheet(title="Daily Check-ins", rows=1000, cols=5)
                    checkin_sheet.append_row(["user_id", "status", "timestamp"])
                checkin_sheet.append_row([user_id, "reset", timestamp])
                print(f"[DEBUG] Added reset entry for user {user_id} when they stopped")
                
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

# ✅ /milestones command - debug command to check completed milestones
async def check_milestones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.effective_user:
            return
            
        user_id = str(update.effective_user.id)
        rows = worksheet.get_all_records()
        user_row = None
        
        for row in rows:
            if str(row.get('user_id', '')) == str(user_id):
                user_row = row
                break
        
        if not user_row:
            if update.message:
                await update.message.reply_text("❌ User not found in system.")
            return
        
        # Get completed milestones
        feedback_completed = str(user_row.get("feedback_completed", ""))
        completed_list = feedback_completed.split(",") if feedback_completed else []
        completed_list = [x.strip() for x in completed_list if x.strip()]
        
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
            elif entry.get("status") == "reset":
                break
            else:
                break
        
        # Get available milestones
        available_milestones = list(MILESTONE_QUESTIONS.keys())
        
        if update.message:
            message = f"📊 **Milestone Status for User {user_id}**\n\n"
            message += f"🎯 **Current Streak:** {current_streak} days\n\n"
            message += f"✅ **Completed Milestones:** {', '.join(completed_list) if completed_list else 'None'}\n\n"
            message += f"📋 **Available Milestones:** {', '.join(map(str, available_milestones))}\n\n"
            
            # Check which milestones are due
            due_milestones = [m for m in available_milestones if m <= current_streak and str(m) not in completed_list]
            if current_streak == 0:
                message += "🚀 **Status:** No milestones due yet. Keep going to unlock milestone feedback!"
            elif due_milestones:
                message += f"⏰ **Due for Feedback:** {', '.join(map(str, due_milestones))}"
            else:
                message += "🎉 **All due milestones completed!**"
            
            await update.message.reply_text(message, parse_mode="Markdown")
            
    except Exception as e:
        print(f"[ERROR] Error in check_milestones: {e}")
        if update.message:
            await update.message.reply_text("❌ Error checking milestones.")

# Place handle_share_streak above main
async def handle_share_streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    
    await query.answer()
    user_id = str(update.effective_user.id) if update.effective_user else None
    if not user_id:
        return
    
    # Parse group and streak from callback data
    # Expected: streak_share_{group}_{streak} or streak_share_private_{streak}
    data_parts = query.data.split("_")
    if len(data_parts) >= 4 and data_parts[2] != "private":
        group = data_parts[2]
        # streak = data_parts[3]  # Not used, but available if needed
    else:
        group = None
    
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
            elif entry.get("status") == "reset":
                # Stop counting when we hit a reset (user stopped and resumed)
                break
            else:
                # Stop counting on any "no" or other status
                break
        
        if current_streak < 3:
            await query.edit_message_text("🎉 You need at least 3 days to share a milestone! Keep going!")
            return
        
        # Share in group
        if group and group in GROUP_CHAT_IDS:
            group_chat_id = GROUP_CHAT_IDS[group]
            username = ""
            if update.effective_user:
                username = update.effective_user.username or update.effective_user.first_name or "Anonymous"
            target = user_data.get('fasting_target', 'Unknown')
            
            share_message = f"🎉 *Milestone Alert!*\n\n@{username} just hit a *{current_streak}-day streak*! 🚀\n\nKeep inspiring the community!"
            
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
    # User agreed to daily check-ins, prompt for media upload
    context.user_data['onboarding_state'] = 'media_upload'
    await query.edit_message_text(
        "✅ Perfect! I'll check in with you every morning at 9 AM to ask about your progress from the day before.\n\n"
        "🎙️ 🔴 *Highly recommended*: Do you want to record a voice, video, or video note message to yourself as a commitment?\n\n"
        "If you miss 3 days in a row, I'll send it back to you as a reminder of your why.\n\n"
        "Send it here or type /skip if you want to skip this.",
        parse_mode="Markdown"
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
    print(f"[DEBUG] handle_group_selection: extracted group='{group}', GROUP_CHAT_IDS keys={list(GROUP_CHAT_IDS.keys())}")
    context.user_data["group"] = group
    context.user_data['onboarding_state'] = None
    if group == "None":
        await query.edit_message_text("👍 Got it! We'll keep your progress between us. No group sharing unless you want to.")
    else:
        await query.edit_message_text(f"Great! You're in the {group} group.")
    # Ask for baseline Q&A permission
    context.user_data['onboarding_state'] = 'baseline_permission'
    if update.effective_chat:
        consent_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes", callback_data="baseline_permission_yes"),
                InlineKeyboardButton("❌ No", callback_data="baseline_permission_no")
            ]
        ])
        await update.effective_chat.send_message(
            "Is it okay if I ask you a few questions just to know more about your baseline? This will help me track your progress.",
            reply_markup=consent_markup
        )
    return

async def ask_onboarding_baseline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    context.user_data['onboarding_state'] = 'baseline'
    context.user_data['onboarding_baseline_q_idx'] = 0
    context.user_data['onboarding_baseline_answers'] = []
    baseline_questions = [
        {"q": "🧠 On a scale of 1–5, how focused have you felt lately? (1 = totally distracted, 5 = laser focused)", "type": "scale"},
        {"q": "💪 How often do you feel in control of your impulses? (1–5, 1 = always impulsive, 5 = total self-control)", "type": "scale"},
        {"q": "⏰ On a typical day, about how many hours do you spend on the habit that you want to fast on? (e.g., 0.5, 2, 6)", "type": "number"},
        {"q": "🙏 Last thing! Is it okay if we record your feedback to help improve the bot and (anonymously) use your results as marketing stats? Your identity will always be kept private. Thank you so much! 💖", "type": "permission"}
    ]
    context.user_data['onboarding_baseline_questions'] = baseline_questions
    # Ask the first question
    if update.effective_chat:
        q = baseline_questions[0]['q']
        q_type = baseline_questions[0]['type']
        if q_type == 'scale':
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(str(i), callback_data=f"onboarding_scale_{i}") for i in range(1, 6)]
            ])
            await update.effective_chat.send_message(q, reply_markup=reply_markup)
        elif q_type == 'permission':
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes", callback_data="onboarding_permission_yes"), InlineKeyboardButton("❌ No", callback_data="onboarding_permission_no")]
            ])
            await update.effective_chat.send_message(q, reply_markup=reply_markup)
        else:
            await update.effective_chat.send_message(q)

async def finalize_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    try:
        if not update.effective_user:
            return
        user_id = str(update.effective_user.id)
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
                str(group), "active", str(reminder), str(media_id), str(media_type), "", ""
            ])
        
        # Add a "reset" entry for new users to ensure clean streak start
        timestamp = get_pht_timestamp()
        try:
            checkin_sheet = gc.open_by_key(SHEET_ID).worksheet("Daily Check-ins")
        except Exception as e:
            checkin_sheet = gc.open_by_key(SHEET_ID).add_worksheet(title="Daily Check-ins", rows=1000, cols=5)
            checkin_sheet.append_row(["user_id", "status", "timestamp"])
        checkin_sheet.append_row([user_id, "reset", timestamp])
        print(f"[DEBUG] Added reset entry for new user {user_id} during onboarding")
        
        # Always send the final onboarding message
        if update.message and hasattr(update.message, 'reply_text'):
            await update.message.reply_text("🚀 You're all set! I'll check in with you starting tomorrow at 9 AM. Have a great rest of your day!")
        elif update.callback_query and update.callback_query.message and hasattr(update.callback_query.message, 'reply_text'):
            await update.callback_query.message.reply_text("🚀 You're all set! I'll check in with you starting tomorrow at 9 AM. Have a great rest of your day!")
        context.user_data['onboarding_state'] = None
        # Save onboarding baseline answers to feedback_sheet
        baseline_questions = [
            "🧠 On a scale of 1–5, how focused have you felt lately? (1 = totally distracted, 5 = laser focused)",
            "💪 How often do you feel in control of your impulses? (1–5, 1 = always impulsive, 5 = total self-control)",
            "⏰ On a typical day, about how many hours do you spend on the habit that you want to fast on? (e.g., 0.5, 2, 6)",
            "🙏 Last thing! Is it okay if we record your feedback to help improve the bot and (anonymously) use your results as marketing stats? Your identity will always be kept private. Thank you so much! 💖"
        ]
        baseline_answers = context.user_data.get('onboarding_baseline_answers')
        if not isinstance(baseline_answers, list):
            baseline_answers = []
        for idx, (q, a) in enumerate(zip(baseline_questions, baseline_answers)):
            permission = ''
            if idx == 3:
                permission = a
            feedback_sheet.append_row([
                str(user_id), str(username), 'Onboarding', q, a, get_pht_timestamp(), str(permission)
            ])
    except Exception as e:
        print(f"[ERROR] Error in finalize_onboarding: {e}")
        if update.message and hasattr(update.message, 'reply_text'):
            await update.message.reply_text("There was an error saving your onboarding info. Please try /start again.")

async def handle_media_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    if context.user_data.get('onboarding_state') != 'media_upload':
        return
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
            await update.message.reply_text("❌ Please send a *voice*, *video*, *video note*, or *audio* message as your commitment, or type /skip to skip this step.", parse_mode="Markdown")
        return
    file_id = file.file_id
    context.user_data["reminder_media_id"] = file_id
    context.user_data["reminder_media_type"] = media_type
    context.user_data["waiting_for_media"] = False
    context.user_data['onboarding_state'] = 'group'
    if update.message and hasattr(update.message, 'reply_text'):
        await update.message.reply_text("🎧 Got it! I'll keep this and send it if you miss 3 days in a row.")
        await update.message.reply_text(
            "Which accountability group are you part of?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎮 GameBreak", callback_data="group_GameBreak")],
                [InlineKeyboardButton("⛔ NoFap", callback_data="group_NoFap")],
                [InlineKeyboardButton("📵 ScreenBreak", callback_data="group_ScreenBreak")],
                [InlineKeyboardButton("🙅 Not part of any group", callback_data="group_None")]
            ])
        )

async def skip_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    if context.user_data.get('onboarding_state') != 'media_upload':
        return
    context.user_data["reminder_media_id"] = None
    context.user_data["reminder_media_type"] = None
    context.user_data["waiting_for_media"] = False
    context.user_data['onboarding_state'] = 'group'
    if update.message and hasattr(update.message, 'reply_text'):
        await update.message.reply_text("👍 No worries. We'll skip this part.")
        await update.message.reply_text(
            "Which accountability group are you part of?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎮 GameBreak", callback_data="group_GameBreak")],
                [InlineKeyboardButton("⛔ NoFap", callback_data="group_NoFap")],
                [InlineKeyboardButton("📵 ScreenBreak", callback_data="group_ScreenBreak")],
                [InlineKeyboardButton("🙅 Not part of any group", callback_data="group_None")]
            ])
        )

# Scheduler functions for each group
async def send_group_text_prompt(app, group_key):
    """Send the next text prompt for a specific group."""
    try:
        chat_id = GROUP_CHAT_IDS[group_key]
        current_index = GROUP_PROMPT_INDEX[group_key]
        
        # Get the text prompt at current index
        text_prompts = GROUP_PROMPTS[group_key]["text"]
        if current_index < len(text_prompts):
            prompt = text_prompts[current_index]
            await app.bot.send_message(chat_id=chat_id, text=prompt)
            print(f"[DEBUG] Sent text prompt #{current_index + 1} to {group_key}")
        else:
            print(f"[DEBUG] No more text prompts for {group_key}")
            
    except Exception as e:
        print(f"[ERROR] Error sending text prompt to {group_key}: {e}")

async def send_group_poll_prompt(app, group_key):
    """Send the next poll prompt for a specific group."""
    try:
        chat_id = GROUP_CHAT_IDS[group_key]
        current_index = GROUP_PROMPT_INDEX[group_key]
        
        # Get the poll prompt at current index
        poll_prompts = GROUP_PROMPTS[group_key]["polls"]
        if current_index < len(poll_prompts):
            poll = poll_prompts[current_index]
            await app.bot.send_poll(
                chat_id=chat_id, 
                question=poll["question"], 
                options=poll["options"], 
                is_anonymous=False
            )
            print(f"[DEBUG] Sent poll prompt #{current_index + 1} to {group_key}")
        else:
            print(f"[DEBUG] No more poll prompts for {group_key}")
            
    except Exception as e:
        print(f"[ERROR] Error sending poll prompt to {group_key}: {e}")

def advance_group_prompt_index(group_key):
    """Advance the prompt index for a group and reset if needed."""
    GROUP_PROMPT_INDEX[group_key] += 1
    # Reset to 0 if we've gone through all prompts (24 total: 12 text + 12 polls)
    if GROUP_PROMPT_INDEX[group_key] >= 24:
        GROUP_PROMPT_INDEX[group_key] = 0
        print(f"[DEBUG] Reset prompt index for {group_key} to 0")

# Scheduler functions for each group
async def send_general_monday_prompt(app):
    """Send text prompt to General group on Monday."""
    await send_group_text_prompt(app, "General")
    advance_group_prompt_index("General")

async def send_general_friday_prompt(app):
    """Send poll prompt to General group on Friday."""
    await send_group_poll_prompt(app, "General")
    advance_group_prompt_index("General")

async def send_nofap_tuesday_prompt(app):
    """Send text prompt to NoFap group on Tuesday."""
    await send_group_text_prompt(app, "NoFap")
    advance_group_prompt_index("NoFap")

async def send_nofap_thursday_prompt(app):
    """Send poll prompt to NoFap group on Thursday."""
    await send_group_poll_prompt(app, "NoFap")
    advance_group_prompt_index("NoFap")

async def send_screenbreak_tuesday_prompt(app):
    """Send text prompt to ScreenBreak group on Tuesday."""
    await send_group_text_prompt(app, "ScreenBreak")
    advance_group_prompt_index("ScreenBreak")

async def send_screenbreak_thursday_prompt(app):
    """Send poll prompt to ScreenBreak group on Thursday."""
    await send_group_poll_prompt(app, "ScreenBreak")
    advance_group_prompt_index("ScreenBreak")

async def send_gamebreak_tuesday_prompt(app):
    """Send text prompt to GameBreak group on Tuesday."""
    await send_group_text_prompt(app, "GameBreak")
    advance_group_prompt_index("GameBreak")

async def send_gamebreak_thursday_prompt(app):
    """Send poll prompt to GameBreak group on Thursday."""
    await send_group_poll_prompt(app, "GameBreak")
    advance_group_prompt_index("GameBreak")

async def send_moneytalk_wednesday_prompt(app):
    """Send text prompt to Moneytalk group on Wednesday."""
    await send_group_text_prompt(app, "Moneytalk")
    advance_group_prompt_index("Moneytalk")

async def send_moneytalk_saturday_prompt(app):
    """Send poll prompt to Moneytalk group on Saturday."""
    await send_group_poll_prompt(app, "Moneytalk")
    advance_group_prompt_index("Moneytalk")

async def test_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test command to manually trigger group prompts."""
    if not update.message or not update.message.text:
        return
    
    # Parse the command: /testprompt <group_name>
    command_parts = update.message.text.split()
    if len(command_parts) != 2:
        await update.message.reply_text(
            "Usage: /testprompt <group_name>\n"
            "Available groups: General, NoFap, ScreenBreak, GameBreak, Moneytalk\n"
            "Example: /testprompt General"
        )
        return
    
    group_name = command_parts[1]
    if group_name not in GROUP_CHAT_IDS:
        await update.message.reply_text(
            f"Invalid group name: {group_name}\n"
            "Available groups: General, NoFap, ScreenBreak, GameBreak, Moneytalk"
        )
        return
    
    try:
        # Send the next text prompt for the group
        await send_group_text_prompt(context.application, group_name)
        await update.message.reply_text(f"✅ Sent text prompt to {group_name}")
        
        # Also send the next poll prompt
        await send_group_poll_prompt(context.application, group_name)
        await update.message.reply_text(f"✅ Sent poll prompt to {group_name}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error testing prompts: {e}")

# --- Feedback Question Sending Stub ---
async def send_next_feedback_question(update, context):
    pending = context.user_data.get('pending_feedback')
    if not pending:
        return
    milestone = pending['milestone']
    q_idx = pending['q_idx']
    questions = MILESTONE_QUESTIONS.get(milestone, [])
    
    # Send introductory message for 7+ day milestones on first question
    if milestone >= 7 and q_idx == 0:
        if update.effective_chat:
            await update.effective_chat.send_message("📊 Quick check-in since you started! 🎯")
    
    # For milestone 7, 14, 30, 60, 90: thank after the last question (now 3rd)
    if milestone in [7, 14, 30, 60, 90] and q_idx >= len(questions):
        if update.effective_chat:
            await update.effective_chat.send_message("🙏 Thank you for your feedback! Your answers help us improve and inspire others. 💡✨")
        
        # Mark this milestone as completed in the user's record
        user_id = pending.get('user_id')
        if user_id:
            try:
                rows = worksheet.get_all_records()
                for i, row in enumerate(rows):
                    if str(row.get('user_id', '')) == str(user_id):
                        # Get current completed milestones
                        feedback_completed = str(row.get("feedback_completed", ""))
                        completed_list = feedback_completed.split(",") if feedback_completed else []
                        completed_list = [x.strip() for x in completed_list if x.strip()]
                        
                        # Add this milestone if not already present
                        if str(milestone) not in completed_list:
                            completed_list.append(str(milestone))
                        
                        # Update the sheet
                        new_feedback_completed = ",".join(completed_list)
                        worksheet.update_cell(i + 2, SHEET_COLUMNS['FEEDBACK_COMPLETED'], new_feedback_completed)
                        print(f"[DEBUG] Marked milestone {milestone} as completed for user {user_id}. Updated list: {new_feedback_completed}")
                        break
            except Exception as e:
                print(f"[ERROR] Failed to mark milestone {milestone} as completed for user {user_id}: {e}")
        
        context.user_data.pop('pending_feedback', None)
        return
    if q_idx >= len(questions):
        if milestone in []:
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("Yes", callback_data="milestone_testimonial_yes"), InlineKeyboardButton("No", callback_data="milestone_testimonial_no")]
            ])
            await update.effective_chat.send_message(
                "Would you like to share a testimonial about your journey so far? (How you've transmuted your dopamine addictions, what changed, etc.)", reply_markup=reply_markup
            )
            context.user_data['pending_milestone_testimonial'] = {
                'user_id': pending['user_id'],
                'username': pending['username'],
                'milestone': milestone,
                'timestamp': get_pht_timestamp(),
                'step': 'ask_testimonial',
                'testimonial': ''
            }
            context.user_data.pop('pending_feedback', None)
            return
        else:
            if update.effective_chat:
                await update.effective_chat.send_message("Thank you for your feedback! Your answers help us improve and inspire others.")
            
            # Mark this milestone as completed in the user's record
            user_id = pending.get('user_id')
            if user_id:
                try:
                    rows = worksheet.get_all_records()
                    for i, row in enumerate(rows):
                        if str(row.get('user_id', '')) == str(user_id):
                            # Get current completed milestones
                            feedback_completed = str(row.get("feedback_completed", ""))
                            completed_list = feedback_completed.split(",") if feedback_completed else []
                            completed_list = [x.strip() for x in completed_list if x.strip()]
                            
                            # Add this milestone if not already present
                            if str(milestone) not in completed_list:
                                completed_list.append(str(milestone))
                            
                            # Update the sheet
                            new_feedback_completed = ",".join(completed_list)
                            worksheet.update_cell(i + 2, SHEET_COLUMNS['FEEDBACK_COMPLETED'], new_feedback_completed)
                            print(f"[DEBUG] Marked milestone {milestone} as completed for user {user_id}. Updated list: {new_feedback_completed}")
                            break
                except Exception as e:
                    print(f"[ERROR] Failed to mark milestone {milestone} as completed for user {user_id}: {e}")
            
            context.user_data.pop('pending_feedback', None)
        return
    q = questions[q_idx]['q']
    q_type = questions[q_idx]['type']
    if q_type == 'yesno':
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data="feedback_yes"), InlineKeyboardButton("❌ No", callback_data="feedback_no")]
        ])
        await update.effective_chat.send_message(q, reply_markup=reply_markup)
    elif q_type == 'scale':
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(str(i), callback_data=f"feedback_scale_{i}") for i in range(1, 6)]
        ])
        await update.effective_chat.send_message(q, reply_markup=reply_markup)
    elif q_type == 'number':
        await update.effective_chat.send_message(q + " (Please reply with a number)")
    elif q_type == 'text':
        await update.effective_chat.send_message(q + " (Please reply with your answer)")
    else:
        await update.effective_chat.send_message(q)

# --- Feedback Answer Handler ---
async def handle_feedback_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[DEBUG] handle_feedback_response called")
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    pending = context.user_data.get('pending_feedback')
    if not pending:
        print("[DEBUG] No pending feedback, allowing fallthrough")
        return False  # Allow fallthrough to main handler
    milestone = pending['milestone']
    q_idx = pending['q_idx']
    questions = MILESTONE_QUESTIONS.get(milestone, [])
    if q_idx >= len(questions):
        context.user_data.pop('pending_feedback', None)
        return False
    q = questions[q_idx]['q']
    q_type = questions[q_idx]['type']
    answer = None
    permission = ''
    if update.callback_query:
        data = update.callback_query.data
        await update.callback_query.answer()
        if data == 'feedback_yes':
            answer = 'Yes'
        elif data == 'feedback_no':
            answer = 'No'
        elif data and data.startswith('feedback_scale_'):
            answer = data.split('_')[-1]
        else:
            answer = data or ''
        try:
            await update.callback_query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
    elif update.message and update.message.text:
        answer = update.message.text.strip()
    else:
        return False
    field = questions[q_idx].get('field', '')
    if field in ['permission', 'marketing_permission']:
        permission = answer
    feedback_sheet.append_row([
        str(pending['user_id']) if pending['user_id'] is not None else '',
        str(pending['username']) if pending['username'] is not None else '',
        f"Day {milestone}",
        str(q) if q is not None else '',
        str(answer) if answer is not None else '',
        get_pht_timestamp(),
        str(permission) if permission is not None else ''
    ])
    pending['answers'].append({
        'question': q,
        'answer': answer,
        'field': field
    })
    pending['q_idx'] += 1
    context.user_data['pending_feedback'] = pending
    
    # Send acknowledgment based on question type and milestone
    if milestone >= 7:  # Only for 7+ day milestones (skip 1 and 3 day milestones)
        if q_idx == 0:  # Focus question
            if update.callback_query:
                await update.callback_query.edit_message_text("🧠 Noted! Your focus level is recorded.")
            elif update.message:
                await update.message.reply_text("🧠 Noted! Your focus level is recorded.")
        elif q_idx == 1:  # Impulse control question
            if update.callback_query:
                await update.callback_query.edit_message_text("💪 Got it! Your self-control progress is tracked.")
            elif update.message:
                await update.message.reply_text("💪 Got it! Your self-control progress is tracked.")
        elif q_idx == 2:  # Habit decrease question
            if update.callback_query:
                await update.callback_query.edit_message_text("⏰ Noted! Your habit reduction progress is recorded.")
            elif update.message:
                await update.message.reply_text("⏰ Noted! Your habit reduction progress is recorded.")
    
    # Special case: after 3-day milestone question, show thank you and stop
    if milestone == 3 and pending['q_idx'] >= len(questions):
        if update.callback_query:
            await update.callback_query.edit_message_text("🙏 Thank you for your feedback! Your answers help us improve and inspire others. 💡✨")
        elif update.message:
            await update.message.reply_text("🙏 Thank you for your feedback! Your answers help us improve and inspire others. 💡✨")
        
        # Mark this milestone as completed in the user's record
        user_id = pending.get('user_id')
        if user_id:
            try:
                rows = worksheet.get_all_records()
                for i, row in enumerate(rows):
                    if str(row.get('user_id', '')) == str(user_id):
                        # Get current completed milestones
                        feedback_completed = str(row.get("feedback_completed", ""))
                        completed_list = feedback_completed.split(",") if feedback_completed else []
                        completed_list = [x.strip() for x in completed_list if x.strip()]
                        
                        # Add this milestone if not already present
                        if str(milestone) not in completed_list:
                            completed_list.append(str(milestone))
                        
                        # Update the sheet
                        new_feedback_completed = ",".join(completed_list)
                        worksheet.update_cell(i + 2, SHEET_COLUMNS['FEEDBACK_COMPLETED'], new_feedback_completed)
                        print(f"[DEBUG] Marked milestone {milestone} as completed for user {user_id}. Updated list: {new_feedback_completed}")
                        break
            except Exception as e:
                print(f"[ERROR] Failed to mark milestone {milestone} as completed for user {user_id}: {e}")
        
        context.user_data.pop('pending_feedback', None)
        return False
    await send_next_feedback_question(update, context)
    return True  # Handled successfully

# --- Testimonial Command Handler ---
async def testimonial_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    if not update.effective_user:
        return
    user_id = str(update.effective_user.id)
    username = (update.effective_user.username or update.effective_user.first_name or '') if update.effective_user else ''
    context.user_data['pending_testimonial'] = {
        'user_id': user_id,
        'username': username,
        'timestamp': get_pht_timestamp(),
        'step': 'ask_testimonial',
        'testimonial': ''
    }
    if update.message:
        await update.message.reply_text(
            "Share your story! How has your journey with the bot helped you transmute your dopamine addictions? (We may use your story for marketing, anonymously, with your permission.)"
        )

# --- Testimonial Text/Permission Handler ---
async def handle_testimonial_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[DEBUG] handle_testimonial_response called")
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    pending = context.user_data.get('pending_testimonial')
    if not pending:
        print("[DEBUG] No pending testimonial, allowing fallthrough")
        return False  # Allow fallthrough to main handler
    if pending['step'] == 'ask_testimonial' and update.message and update.message.text:
        pending['testimonial'] = update.message.text.strip()
        pending['step'] = 'ask_permission'
        context.user_data['pending_testimonial'] = pending
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes", callback_data="testimonial_permission_yes"), InlineKeyboardButton("No", callback_data="testimonial_permission_no")]
        ])
        await update.message.reply_text(
            "Can we use your testimonial for marketing (anonymously)?", reply_markup=reply_markup
        )
        return True
    elif pending['step'] == 'ask_permission' and update.callback_query:
        data = update.callback_query.data
        await update.callback_query.answer()
        permission = 'Yes' if data == 'testimonial_permission_yes' else 'No'
        feedback_sheet.append_row([
            pending['user_id'],
            pending['username'],
            'Testimonial',
            'Testimonial',
            pending['testimonial'],
            pending['timestamp'],
            permission
        ])
        context.user_data.pop('pending_testimonial', None)
        await update.callback_query.edit_message_text(
            "Thank you for sharing your story! Keep inspiring others."
        )
        return True
    return False  # Not handled

# --- Handler for milestone testimonial prompt ---
async def handle_milestone_testimonial_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[DEBUG] handle_milestone_testimonial_response called")
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    pending = context.user_data.get('pending_milestone_testimonial')
    if not pending:
        print("[DEBUG] No pending milestone testimonial, allowing fallthrough")
        return False  # Allow fallthrough to main handler
    if update.callback_query:
        data = update.callback_query.data
        await update.callback_query.answer()
        if data == 'milestone_testimonial_yes':
            pending['step'] = 'write_testimonial'
            context.user_data['pending_milestone_testimonial'] = pending
            await update.callback_query.edit_message_text(
                "Awesome! Please write your testimonial below."
            )
            return True
        elif data == 'milestone_testimonial_no':
            context.user_data.pop('pending_milestone_testimonial', None)
            await update.callback_query.edit_message_text(
                "Ok, keep up the great work!"
            )
            return True
    elif pending['step'] == 'write_testimonial' and update.message and update.message.text:
        pending['testimonial'] = update.message.text.strip()
        pending['step'] = 'ask_permission'
        context.user_data['pending_milestone_testimonial'] = pending
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes", callback_data="milestone_testimonial_permission_yes"), InlineKeyboardButton("No", callback_data="milestone_testimonial_permission_no")]
        ])
        await update.message.reply_text(
            "Can we use your testimonial for marketing (anonymously)?", reply_markup=reply_markup
        )
        return True
    elif pending['step'] == 'ask_permission' and update.callback_query:
        data = update.callback_query.data
        await update.callback_query.answer()
        permission = 'Yes' if data == 'milestone_testimonial_permission_yes' else 'No'
        feedback_sheet.append_row([
            pending['user_id'],
            pending['username'],
            f"Day {pending['milestone']} Testimonial",
            'Testimonial',
            pending['testimonial'],
            pending['timestamp'],
            permission
        ])
        context.user_data.pop('pending_milestone_testimonial', None)
        await update.callback_query.edit_message_text(
            "Thank you for sharing your story! Keep inspiring others."
        )
        return True
    return False  # Not handled

# Add this handler function
async def handle_baseline_permission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context, 'user_data') or not isinstance(context.user_data, dict):
        context.user_data = {}
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    if query.data == 'baseline_permission_yes':
        context.user_data['onboarding_baseline_permission'] = 'yes'
        await ask_onboarding_baseline(update, context)
    else:
        context.user_data['onboarding_baseline_permission'] = 'no'
        # Provide a proper response when user declines baseline questions
        if query.message:
            await query.message.reply_text("👍 No problem! We'll skip the baseline questions and get you set up right away.")
        await finalize_onboarding(update, context)

# ✅ Start app
if __name__ == '__main__':
    print("[DEBUG] Entered __main__ block")
    print("[DEBUG] Starting bot setup...")
    app = ApplicationBuilder().token("7070152877:AAEIfwdxiopaawZ-gb55LhabANLgXdYzG-Y").build()

    # Add handlers
    print("[DEBUG] Registering /start handler")
    app.add_handler(CommandHandler("start", start))
    print("[DEBUG] Registered /start handler")
    print("[DEBUG] Registering /stop handler")
    app.add_handler(CommandHandler("stop", stop_tracking))
    print("[DEBUG] Registered /stop handler")
    print("[DEBUG] Registering /reset handler")
    app.add_handler(CommandHandler("reset", reset_streak))
    print("[DEBUG] Registered /reset handler")
    print("[DEBUG] Registering /milestones handler")
    app.add_handler(CommandHandler("milestones", check_milestones))
    print("[DEBUG] Registered /milestones handler")
    print("[DEBUG] Registering /testprompt handler")
    app.add_handler(CommandHandler("testprompt", test_prompt))
    print("[DEBUG] Registered /testprompt handler")
    print("[DEBUG] Registering checkin callback handler")
    app.add_handler(CallbackQueryHandler(handle_checkin_response, pattern="^checkin_"))
    print("[DEBUG] Registered checkin callback handler")
    
    # --- SPECIALIZED HANDLERS (only handle specific cases) ---
    # print("[DEBUG] Registering feedback text handler (priority)")
    # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback_response, block=False))
    # print("[DEBUG] Registered feedback text handler (priority)")
    # print("[DEBUG] Registering testimonial response handler (priority)")
    # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_testimonial_response, block=False))
    # print("[DEBUG] Registered testimonial response handler (priority)")
    # print("[DEBUG] Registering milestone testimonial response handler (priority)")
    # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_milestone_testimonial_response, block=False))
    # print("[DEBUG] Registered milestone testimonial response handler (priority)")
    
    # --- MAIN MESSAGE HANDLER (for onboarding and general conversation) ---
    print("[DEBUG] Registering main message handler (onboarding/conversation)")
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("[DEBUG] Registered main message handler")
    print("[DEBUG] Registering share streak callback handler")
    app.add_handler(CallbackQueryHandler(handle_share_streak, pattern="^streak_share_"))
    print("[DEBUG] Registered share streak callback handler")
    print("[DEBUG] Registering reminder consent callback handler")
    app.add_handler(CallbackQueryHandler(handle_reminder_consent, pattern="^reminder_"))
    print("[DEBUG] Registered reminder consent callback handler")
    print("[DEBUG] Registering group selection callback handler")
    app.add_handler(CallbackQueryHandler(handle_group_selection, pattern="group_"))
    print("[DEBUG] Registered group selection callback handler")
    print("[DEBUG] Registering media upload handler")
    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE | filters.Document.ALL,
        handle_media_upload
    ))
    print("[DEBUG] Registered media upload handler")
    # --- FIX: Register onboarding_scale_ callback to handle_message before onboarding_ ---
    print("[DEBUG] Registering onboarding scale callback handler (for baseline Q&A)")
    app.add_handler(CallbackQueryHandler(handle_message, pattern="^onboarding_scale_"))
    print("[DEBUG] Registered onboarding scale callback handler (for baseline Q&A)")
    print("[DEBUG] Registering onboarding permission callback handler (for baseline Q&A)")
    app.add_handler(CallbackQueryHandler(handle_message, pattern="^onboarding_permission_"))
    print("[DEBUG] Registered onboarding permission callback handler (for baseline Q&A)")
    print("[DEBUG] Registering onboarding choice handler")
    app.add_handler(CallbackQueryHandler(handle_onboarding_choice, pattern="^onboarding_"))
    print("[DEBUG] Registered onboarding choice handler")
    print("[DEBUG] Registering /skip handler")
    app.add_handler(CommandHandler("skip", skip_media))
    print("[DEBUG] Registered /skip handler")
    print("[DEBUG] Registering new member handler")
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    print("[DEBUG] Registered new member handler")
    print("[DEBUG] Registering welcome start callback handler")
    app.add_handler(CallbackQueryHandler(handle_welcome_start, pattern="^welcome_start$"))
    print("[DEBUG] Registered welcome start callback handler")
    # --- Feedback Handlers ---
    print("[DEBUG] Registering feedback callback handler")
    app.add_handler(CallbackQueryHandler(handle_feedback_response, pattern="^feedback_"))
    print("[DEBUG] Registered feedback callback handler")
    print("[DEBUG] Registering baseline permission callback handler")
    app.add_handler(CallbackQueryHandler(handle_baseline_permission_callback, pattern="^baseline_permission_"))
    print("[DEBUG] Registered baseline permission callback handler")
    print("[DEBUG] All handlers registered. Starting scheduler and polling...")
    loop = asyncio.get_event_loop()
    scheduler = BackgroundScheduler()
    
    # Schedule daily check-ins
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(send_daily_checkins(app), loop), 'interval', seconds=CHECKIN_INTERVAL_SECONDS)
    
    # Schedule group prompts - all at 9AM PHT (UTC+8)
    # General: Monday (text) + Friday (poll)
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_general_monday_prompt(app), loop),
        CronTrigger(day_of_week='mon', hour=9, minute=0, timezone='Asia/Manila')
    )
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_general_friday_prompt(app), loop),
        CronTrigger(day_of_week='fri', hour=9, minute=0, timezone='Asia/Manila')
    )
    
    # NoFap: Tuesday (text) + Thursday (poll)
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_nofap_tuesday_prompt(app), loop),
        CronTrigger(day_of_week='tue', hour=9, minute=0, timezone='Asia/Manila')
    )
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_nofap_thursday_prompt(app), loop),
        CronTrigger(day_of_week='thu', hour=9, minute=0, timezone='Asia/Manila')
    )
    
    # ScreenBreak: Tuesday (text) + Thursday (poll)
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_screenbreak_tuesday_prompt(app), loop),
        CronTrigger(day_of_week='tue', hour=9, minute=0, timezone='Asia/Manila')
    )
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_screenbreak_thursday_prompt(app), loop),
        CronTrigger(day_of_week='thu', hour=9, minute=0, timezone='Asia/Manila')
    )
    
    # GameBreak: Tuesday (text) + Thursday (poll)
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_gamebreak_tuesday_prompt(app), loop),
        CronTrigger(day_of_week='tue', hour=9, minute=0, timezone='Asia/Manila')
    )
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_gamebreak_thursday_prompt(app), loop),
        CronTrigger(day_of_week='thu', hour=9, minute=0, timezone='Asia/Manila')
    )
    
    # Moneytalk: Wednesday (text) + Saturday (poll)
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_moneytalk_wednesday_prompt(app), loop),
        CronTrigger(day_of_week='wed', hour=9, minute=0, timezone='Asia/Manila')
    )
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_moneytalk_saturday_prompt(app), loop),
        CronTrigger(day_of_week='sat', hour=9, minute=0, timezone='Asia/Manila')
    )
    
    scheduler.start()
    print("✅ Bot is running... waiting for Telegram messages.")
    print("📅 Group prompts scheduled:")
    print("   - General: Monday 9AM (text) + Friday 9AM (poll)")
    print("   - NoFap: Tuesday 9AM (text) + Thursday 9AM (poll)")
    print("   - ScreenBreak: Tuesday 9AM (text) + Thursday 9AM (poll)")
    print("   - GameBreak: Tuesday 9AM (text) + Thursday 9AM (poll)")
    print("   - Moneytalk: Wednesday 9AM (text) + Saturday 9AM (poll)")
    print("[DEBUG] About to start polling loop")
    app.run_polling()

