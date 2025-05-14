---
title: Solana SuperTeam Admin Bot
emoji: 🔑
colorFrom: green
colorTo: blue
sdk: docker
sdk_version: "latest"
app_file: app.py
pinned: false
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference

# Solana SuperTeam Admin Bot

This bot allows administrators to manage information for Solana SuperTeam members, including events, FAQs, and emergency information.

## Features

- Events Management: Create, edit, and remove events in the calendar
- FAQ Management: Add, update, and delete frequently asked questions
- Emergency Information: Update emergency contacts and procedures
- User Stats: View usage statistics for the User Bot
- Admin Dashboard: Web interface for content management
- WebSocket Monitoring: Receive real-time notifications when the system responds with "I'm sorry" messages

## Commands

- `/start` - Start the bot and display the admin menu
- `/addevent` - Create a new event
- `/addfaq` - Add a new FAQ entry
- `/updateemergency` - Update emergency information
- `/stats` - View user statistics
- `/status` - Check connection status of services
- `/help` - Display admin help information

## Interface

When you start the bot, you'll be presented with an admin menu offering the following options:
- Manage Events
- Manage FAQs
- Update Emergency Info
- View User Stats
- Settings
- Help

## WebSocket Monitoring

The Admin Bot connects to the backend via WebSocket to receive real-time notifications when the system responds to users with messages beginning with "I'm sorry". This allows administrators to:

1. Monitor situations where the system cannot answer user questions
2. Identify common issues and knowledge gaps
3. Improve the system's capabilities based on real user interactions

When a user receives an "I'm sorry" response, the Admin Bot will immediately notify administrators with:
- User information
- The original user question
- The system's response
- Session ID for reference

### WebSocket Configuration

The WebSocket connection is automatically established when the bot starts. It uses the following environment variables:

```
ADMIN_ID=admin-bot-123            # Unique identifier for this admin
WEBSOCKET_SERVER=backend.example.com  # WebSocket server hostname
WEBSOCKET_PORT=443                # WebSocket server port
WEBSOCKET_PATH=/admin/ws/monitor/  # WebSocket endpoint path
```

The bot automatically reconnects if the connection is lost and sends regular ping messages to keep the connection alive.

## Setup

### Local Development

1. Clone this repository
2. Create a `.env` file with the following variables:
   ```
   TELEGRAM_BOT_TOKEN=your_admin_bot_token
   API_DATABASE_URL=your_database_api_url
   USER_BOT_TOKEN=your_user_bot_token
   ADMIN_ID=admin-bot-123
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
docker build -t solana-adminbot .
docker run -d -p 7861:7861 --name solana-adminbot solana-adminbot
```

### Hugging Face Deployment

This bot is designed to be deployed on Hugging Face Spaces. Follow these steps:

1. Create a new Space on Hugging Face:
   - Go to https://huggingface.co/spaces
   - Click "Create new Space"
   - Choose "Docker" as the Space SDK
   - Set visibility as "Private" (recommended for admin tools)

2. Connect your GitHub repository or upload the files directly:
   - For GitHub: Use the "Import from GitHub" option and select your repository
   - For direct upload: Use the "Files" tab to upload your project files

3. Configure environment variables in the Space settings:
   - Go to the "Settings" tab in your Space
   - Under "Repository secrets", add the following:
     - `TELEGRAM_BOT_TOKEN` - Your Admin bot token
     - `API_DATABASE_URL` - URL for the database API
     - `USER_BOT_TOKEN` - Token for the User bot (required for pushing notifications)
     - `WEBHOOK_URL` - Your Hugging Face Space URL (e.g., https://username-repo-name.hf.space)
     - `ADMIN_ID` - Unique identifier for this admin instance (e.g., admin-bot-123)
     - `ADMIN_GROUP_CHAT_ID` - Telegram chat ID for the admin group to receive notifications

4. Configure hardware in Space settings:
   - CPU: Basic (recommended)
   - No GPU needed for this bot

5. The bot will automatically start running when deployed to Hugging Face

6. Set up Telegram webhook (separate step after deployment):
   - After deployment is complete, run the provided `setup_webhook.py` script:
     ```bash
     # Run in the Space terminal
     cd /app && python setup_webhook.py
     ```
   - Make sure you've configured ADMIN_TELEGRAM_BOT_TOKEN and WEBHOOK_URL in environment variables
   - You should see a success message confirming the webhook was set
   - To verify webhook status: `https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo`

7. Test the bot:
   - Visit your bot on Telegram and send the `/start` command
   - You should see the admin menu appear
   - Check the Space logs if you encounter any issues

## API Endpoints

This bot interacts with the following API endpoints:

### PostgreSQL Endpoints
- `/postgres/faq` - Manage FAQ entries
- `/postgres/emergency` - Manage emergency information
- `/postgres/events` - Manage events
- `/postgres/users` - View user statistics

### Admin Endpoints
- `/admin/dashboard` - Web interface for content management
- `/admin/webhook` - Configure webhook settings
- `/admin/notifications` - Send notifications to users
- `/admin/ws/monitor/{admin_id}` - WebSocket endpoint for monitoring "I'm sorry" responses
- `/admin/ws/status/{admin_id}` - Check status of admin WebSocket connection
- `/admin/ws/status` - View all admin connections

### Health Check
- `/health` - Check overall API health

## Web Interface

When deployed, the bot provides an admin dashboard web interface for managing content and viewing statistics. You can access this interface at:
```
https://your-space-url/admin/dashboard
```

## Project Structure

```
.
├── main.py              # Main bot logic
├── app.py               # FastAPI app for deployment
├── setup_webhook.py     # Script to configure Telegram webhook
├── admin/               # Admin dashboard interface
├── .env                 # Environment variables (not included in git)
├── requirements.txt     # Python dependencies
├── Dockerfile           # Docker configuration
├── .gitignore           # Git ignore configuration
├── websocket_admin_bot_guide.md  # Documentation for the Admin WebSocket
└── README.md            # Documentation
```

## Troubleshooting

If you encounter issues with the bot:

1. **Connection Issues**:
   - Verify your Telegram connection
   - Check that the bot token is correct
   - Run the setup_webhook.py script to configure the webhook

2. **API Access**:
   - Ensure API endpoints are accessible from the Space
   - Check that database connection string is correct

3. **Webhook Issues**: 
   - Run the setup_webhook.py script to reconfigure the webhook
   - Check that the URL format is correct (https://{username}-{repo-name}.hf.space/telegram-webhook)
   - Verify with getWebhookInfo API that webhook is correctly set

4. **WebSocket Issues**:
   - Use the `/status` command to check if the WebSocket connection is active
   - Verify that the backend server supports the WebSocket protocol
   - Check that the ADMIN_ID is configured correctly
   - Look for WebSocket-related errors in the logs

5. **Space Errors**:
   - Check the logs tab in your Space for error messages
   - Restart the Space if needed using the "Factory reboot" option

6. **Content Management**:
   - If you cannot add or edit content, check the database connection
   - Verify the User Bot has access to the updated content

For support or bug reports, please contact the development team.

## Privacy Policy

This bot requires admin privileges and handles sensitive information. All data is stored securely and access is restricted to authorized administrators only.

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