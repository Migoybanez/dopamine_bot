# 🚀 Dopamine Bot Deployment Guide

## Quick Setup (Railway - Recommended)

### Step 1: Prepare Your Code
1. Make sure you have these files in your project:
   - `mainv3wgpt.py` (your bot code)
   - `requirements.txt` (dependencies)
   - `Procfile` (tells Railway how to run the bot)
   - `runtime.txt` (Python version)
   - `dopamine_bot_credentials.json` (Google Sheets credentials)

### Step 2: Set Up Railway
1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Connect your GitHub repository
5. Railway will automatically detect it's a Python project

### Step 3: Configure Environment Variables
In Railway dashboard, go to your project → "Variables" tab and add:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
OPENAI_API_KEY=your_openai_api_key
DOPAMINE_BOT_CREDENTIALS={"your":"google_credentials_json_here"}
```

### Step 4: Upload Credentials File
1. In Railway dashboard → "Settings" → "Files"
2. Upload your `dopamine_bot_credentials.json` file
3. Set the path as: `dopamine_bot_credentials.json`

### Step 5: Deploy
1. Railway will automatically deploy when you push to GitHub
2. Or click "Deploy" in the Railway dashboard
3. Check the logs to make sure it's running

## Alternative: Heroku Deployment

### Step 1: Install Heroku CLI
```bash
# macOS
brew install heroku/brew/heroku

# Windows
# Download from heroku.com
```

### Step 2: Login and Create App
```bash
heroku login
heroku create your-dopamine-bot-name
```

### Step 3: Set Environment Variables
```bash
heroku config:set TELEGRAM_BOT_TOKEN=your_bot_token
heroku config:set OPENAI_API_KEY=your_openai_api_key
```

### Step 4: Upload Credentials
```bash
heroku config:set DOPAMINE_BOT_CREDENTIALS="$(cat dopamine_bot_credentials.json)"
```

### Step 5: Deploy
```bash
git add .
git commit -m "Deploy bot"
git push heroku main
```

## Alternative: VPS Deployment

### Step 1: Get a VPS
- **Linode**: $5/month
- **Vultr**: $2.50/month
- **DigitalOcean**: $5/month

### Step 2: Connect to VPS
```bash
ssh root@your_server_ip
```

### Step 3: Install Dependencies
```bash
# Update system
apt update && apt upgrade -y

# Install Python and pip
apt install python3 python3-pip python3-venv -y

# Install screen (for keeping bot running)
apt install screen -y
```

### Step 4: Upload Your Code
```bash
# Create directory
mkdir dopamine_bot
cd dopamine_bot

# Upload your files (use scp or git)
# Then create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 5: Set Environment Variables
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export OPENAI_API_KEY="your_openai_api_key"
```

### Step 6: Run the Bot
```bash
# Start a screen session
screen -S dopamine_bot

# Run the bot
python3 mainv3wgpt.py

# Detach from screen: Ctrl+A, then D
# Reattach: screen -r dopamine_bot
```

## 🔧 Environment Variables Setup

### Required Variables:
- `TELEGRAM_BOT_TOKEN`: Your bot token from @BotFather
- `OPENAI_API_KEY`: Your OpenAI API key
- `DOPAMINE_BOT_CREDENTIALS`: Google Sheets credentials JSON

### Optional Variables:
- `DOPAMINE_BOT_CREDENTIALS_FILE`: Path to credentials file (default: "dopamine_bot_credentials.json")

## 📊 Monitoring Your Bot

### Railway/Heroku:
- Check logs in the dashboard
- Set up alerts for errors
- Monitor resource usage

### VPS:
```bash
# Check if bot is running
ps aux | grep python

# View logs
tail -f bot.log

# Restart bot
screen -r dopamine_bot
# Ctrl+C to stop, then run again
```

## 🔒 Security Considerations

1. **Never commit sensitive files**:
   - Add `dopamine_bot_credentials.json` to `.gitignore`
   - Use environment variables for API keys

2. **Rate limiting**:
   - Monitor API usage
   - Set up alerts for high usage

3. **Backup your data**:
   - Google Sheets data is automatically backed up
   - Consider backing up bot logs

## 🚀 Scaling for Community

### For 100+ Users:
- Railway/Heroku free tier should handle this fine
- Monitor API usage and costs

### For 1000+ Users:
- Consider upgrading to paid tier
- Implement rate limiting
- Monitor Google Sheets API quotas

### For 10,000+ Users:
- Consider dedicated VPS
- Implement database instead of Google Sheets
- Set up load balancing

## 💰 Cost Estimates

### Railway:
- Free tier: 500 hours/month
- Paid: $5/month for unlimited

### Heroku:
- Free tier: 550 hours/month
- Paid: $7/month for unlimited

### VPS:
- Linode: $5/month
- Vultr: $2.50/month

## 🎯 Next Steps

1. **Choose your deployment platform**
2. **Set up environment variables**
3. **Deploy and test**
4. **Share your bot with your community**
5. **Monitor usage and performance**

Your bot will be available 24/7 and can handle your entire community! 🚀 