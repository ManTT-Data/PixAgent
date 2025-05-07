---
title: Solana SuperTeam User Bot
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
sdk_version: "latest"
app_file: app.py
pinned: false
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference

# Solana SuperTeam User Bot

This bot serves as a central information hub for Solana SuperTeam members, providing access to events, FAQs, and emergency information.

## Features

- Events Calendar: View upcoming and past events with details like time, location, and description
- FAQ Access: Browse and search frequently asked questions about the Solana SuperTeam
- Emergency Information: Quick access to emergency contacts and procedures
- User-friendly Interface: Intuitive menu-based navigation

## Commands

- `/start` - Start the bot and display the main menu
- `/events` - View events calendar
- `/faq` - Browse frequently asked questions
- `/emergency` - Access emergency information
- `/help` - Display help information

## Interface

When you start the bot, you'll be presented with a menu offering the following options:
- View Events
- Browse FAQs
- Emergency Information
- Help

## Setup

### Local Development

1. Clone this repository
2. Create a `.env` file with the following variables:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   API_DATABASE_URL=your_database_api_url
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the bot in development mode:
   ```
   python app.py
   ```

### Docker Deployment

Build and run the Docker container:

```bash
docker build -t solana-userbot .
docker run -d -p 7860:7860 --name solana-userbot solana-userbot
```

### Hugging Face Deployment

This bot is designed to be deployed on Hugging Face Spaces. Follow these steps:

1. Create a new Space on Hugging Face:
   - Go to https://huggingface.co/spaces
   - Click "Create new Space"
   - Choose "Docker" as the Space SDK
   - Set visibility as "Public" (or "Private" if you prefer)

2. Connect your GitHub repository or upload the files directly:
   - For GitHub: Use the "Import from GitHub" option and select your repository
   - For direct upload: Use the "Files" tab to upload your project files
   - Ensure your repository includes the Dockerfile and all necessary files

3. Configure environment variables in the Space settings:
   - Go to the "Settings" tab in your Space
   - Under "Repository secrets", add the following:
     - `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
     - `API_DATABASE_URL` - URL for the database API
     - `WEBHOOK_URL` - Your Hugging Face Space URL (e.g., https://username-repo-name.hf.space)

4. Configure hardware in Space settings:
   - CPU: Basic (recommended)
   - No GPU needed for this bot

5. The bot will automatically start running in webhook mode when deployed to Hugging Face

6. Set up Telegram webhook:
   - After deployment is complete, run the included setup script:
     ```bash
     # Run in the Space terminal
     cd /app && python setup_webhook.py
     ```
   - Make sure you've configured TELEGRAM_BOT_TOKEN and WEBHOOK_URL in environment variables
   - You should see a success message confirming the webhook was set
   - To verify webhook status: `https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo`

7. Test the bot:
   - Visit your bot on Telegram and send the `/start` command
   - You should see the main menu appear
   - Check the Space logs if you encounter any issues

## API Endpoints

This bot interacts with the following API endpoints:

### PostgreSQL Endpoints
- `/postgres/faq` - Retrieve FAQ entries
- `/postgres/emergency` - Retrieve emergency information
- `/postgres/events` - Retrieve events

### Health Check
- `/health` - Check overall API health

## Web Interface

When deployed, the bot provides a simple web interface at the root URL that displays status information and basic usage statistics. You can access this interface by visiting your Space URL.

## Project Structure

```
.
├── main.py              # Main bot logic
├── app.py               # FastAPI app for deployment
├── .env                 # Environment variables (not included in git)
├── requirements.txt     # Python dependencies
├── Dockerfile           # Docker configuration
├── .gitignore           # Git ignore configuration
└── README.md            # Documentation
```

## Troubleshooting

If you encounter issues with the bot:

1. **Connection Issues**:
   - Verify your Telegram connection
   - Check that the bot token is correct

2. **API Access**:
   - Ensure API endpoints are accessible from the Space
   - Check that database connection string is correct

3. **Webhook Issues**: 
   - Confirm the webhook is correctly set with Telegram
   - Check that the URL format is correct (https://{username}-{repo-name}.hf.space/telegram-webhook)

4. **Space Errors**:
   - Check the logs tab in your Space for error messages
   - Restart the Space if needed using the "Factory reboot" option

5. **Content Problems**:
   - If events, FAQs, or emergency info aren't showing, verify the Admin Bot has added content
   - Ensure the database is properly populated

For support or bug reports, please contact the development team.

## Privacy Policy

This bot collects minimal user data required for operation. We do not share your personal information with third parties. User interaction data may be used for improving the bot's functionality.

## Webhook vs. Long Polling

This bot supports both methods for receiving updates from Telegram:

1. **Webhook (Default)**: Telegram sends updates to the bot's URL when new messages arrive.
2. **Long Polling**: The bot continuously checks Telegram for new updates.

Due to SSL certificate issues on Hugging Face Space, the bot currently uses **Long Polling** instead of Webhook. This is configured automatically when the bot starts.

### Switching Between Webhook and Long Polling

- To remove the webhook and use long polling:
  ```
  python fix_webhook.py
  ```

- To set up a webhook (if SSL issues have been resolved):
  ```
  python setup_webhook.py
  ```

Note that using Long Polling will not affect the functionality of the bot. 