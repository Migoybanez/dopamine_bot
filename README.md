# Dopamine Bot - Habit Transformation Telegram Bot

A Telegram bot that helps users break bad habits through daily check-ins, streak tracking, and personalized AI-powered advice.

## Features

- **Daily Check-ins**: Automated daily reminders at 9 AM PHT
- **Streak Tracking**: Track your progress and celebrate milestones
- **Media Commitments**: Record voice/video messages as motivation
- **Group Accountability**: Share milestones in accountability groups
- **AI-Powered Advice**: Get personalized advice using ChatGPT integration
- **Google Sheets Integration**: All data stored in Google Sheets

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the root directory with:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
```

### 3. Google Sheets Setup

1. Create a Google Sheet with the specified structure
2. Add your `credentials.json` file for Google Sheets API access
3. Update the `SHEET_ID` in `main.py` with your sheet ID

### 4. OpenAI API Key

To get your OpenAI API key:
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Create an account or sign in
3. Go to API Keys section
4. Create a new API key
5. Add it to your `.env` file

### 5. Run the Bot

```bash
python main.py
```

## Commands

- `/start` - Begin onboarding and set up daily check-ins
- `/stop` - Stop receiving daily check-ins
- `/reset` - Reset your streak (admin only)

## AI Features

The bot now includes ChatGPT integration for personalized advice. Users can ask questions like:
- "I'm struggling with my streak, any tips?"
- "How do I handle social pressure?"
- "What should I do when I feel like giving up?"

The AI provides context-aware responses based on the user's specific habit target and current streak. 