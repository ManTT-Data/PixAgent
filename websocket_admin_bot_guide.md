# Hướng Dẫn Kết Nối WebSocket từ Telegram Admin Bot vào Backend

## Tổng Quan

Backend của dự án Pix-Agent cung cấp một endpoint WebSocket cho phép Admin Telegram Bot kết nối và nhận thông báo thời gian thực về các phiên chat mới khi hệ thống không thể trả lời câu hỏi của người dùng (câu trả lời bắt đầu bằng "I don't know").

## Cấu Hình WebSocket

Endpoint WebSocket được cấu hình thông qua các biến môi trường sau:

```
# Cấu hình WebSocket
WEBSOCKET_SERVER=localhost
WEBSOCKET_PORT=7860
WEBSOCKET_PATH=/notify
```

URL đầy đủ của WebSocket sẽ là:
```
ws://{WEBSOCKET_SERVER}:{WEBSOCKET_PORT}{WEBSOCKET_PATH}
```

Ví dụ: `ws://localhost:7860/notify`

Nếu sử dụng HTTPS, cần thay `ws://` bằng `wss://`:
```
wss://{WEBSOCKET_SERVER}:{WEBSOCKET_PORT}{WEBSOCKET_PATH}
```

## Tiêu Chí Gửi Thông Báo

Hệ thống sẽ gửi thông báo khi:
1. Một phiên mới được tạo
2. Nội dung trả lời bắt đầu bằng "I don't know"

## Định Dạng Thông Báo

```json
{
  "type": "new_session",
  "timestamp": "2023-04-15 22:30:45",
  "data": {
    "session_id": "123e4567-e89b-12d3-a456-426614174000",
    "user_id": "12345678",
    "message": "Làm thế nào để tìm thông tin liên hệ khẩn cấp?",
    "response": "I don't know how to find emergency contacts",
    "first_name": "Nguyễn",
    "last_name": "Văn A",
    "username": "nguyenvana",
    "created_at": "2023-04-15 22:30:45",
    "action": "asking_freely",
    "factor": "user"
  }
}
```

## Kết Nối từ Telegram Admin Bot

Dưới đây là mã Python để thiết lập kết nối WebSocket từ Admin Bot:

```python
import websocket
import json
import os
import time
import threading
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv()

# Lấy cấu hình WebSocket từ biến môi trường
WEBSOCKET_SERVER = os.getenv("WEBSOCKET_SERVER", "localhost")
WEBSOCKET_PORT = os.getenv("WEBSOCKET_PORT", "7860")
WEBSOCKET_PATH = os.getenv("WEBSOCKET_PATH", "/notify")

# Tạo URL đầy đủ
ws_url = f"ws://{WEBSOCKET_SERVER}:{WEBSOCKET_PORT}{WEBSOCKET_PATH}"

# Nếu sử dụng HTTPS, thay ws:// bằng wss://
# ws_url = f"wss://{WEBSOCKET_SERVER}{WEBSOCKET_PATH}"

# Gửi keepalive định kỳ
def send_keepalive(ws):
    while True:
        try:
            if ws.sock and ws.sock.connected:
                ws.send("keepalive")
                print("Đã gửi tin nhắn keepalive")
            time.sleep(300)  # 5 phút
        except Exception as e:
            print(f"Lỗi khi gửi keepalive: {e}")
            time.sleep(60)

def on_message(ws, message):
    try:
        # Xử lý tin nhắn JSON
        data = json.loads(message)
        print(f"Đã nhận thông báo: {data}")
        
        # Xử lý thông báo, ví dụ: gửi đến Telegram Admin
        if data.get("type") == "new_session":
            session_data = data.get("data", {})
            user_question = session_data.get("message", "")
            user_name = session_data.get("first_name", "Người dùng không xác định")
            
            # Ở đây là mã code để gửi tin nhắn đến Telegram Admin
            print(f"Người dùng {user_name} đã hỏi: {user_question}")
            
            # Ví dụ sử dụng python-telegram-bot
            # bot.send_message(
            #     chat_id=ADMIN_CHAT_ID,
            #     text=f"⚠️ Câu hỏi cần xử lý từ {user_name}:\n\n{user_question}\n\nTrả lời: {session_data.get('response', '')}"
            # )
    except json.JSONDecodeError:
        print(f"Nhận tin nhắn không phải JSON: {message}")
    except Exception as e:
        print(f"Lỗi xử lý tin nhắn: {e}")

def on_error(ws, error):
    print(f"Lỗi WebSocket: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"Kết nối WebSocket đã đóng: code={close_status_code}, message={close_msg}")

def on_open(ws):
    print(f"Kết nối WebSocket đã mở tới {ws_url}")
    # Gửi tin nhắn keepalive định kỳ trong một thread riêng biệt
    keepalive_thread = threading.Thread(target=send_keepalive, args=(ws,), daemon=True)
    keepalive_thread.start()

def run_forever_with_reconnect():
    while True:
        try:
            # Kết nối WebSocket với ping để duy trì kết nối
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever(ping_interval=60, ping_timeout=30)
            print("Kết nối WebSocket bị mất, kết nối lại sau 5 giây...")
            time.sleep(5)
        except Exception as e:
            print(f"Lỗi kết nối WebSocket: {e}")
            time.sleep(5)

# Bắt đầu client WebSocket trong một thread riêng biệt
websocket_thread = threading.Thread(target=run_forever_with_reconnect, daemon=True)
websocket_thread.start()

# Giữ cho chương trình chạy
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Dừng client WebSocket...")
```

## Tích Hợp vào Telegram Bot

Để tích hợp WebSocket client vào bot Telegram hiện có, hãy làm theo các bước sau:

1. Thêm mã WebSocket vào dự án bot Telegram của bạn
2. Khởi tạo kết nối WebSocket khi bot khởi động
3. Khi nhận được thông báo từ WebSocket, xử lý và gửi tin nhắn đến admin qua Telegram

Ví dụ tích hợp sử dụng thư viện python-telegram-bot:

```python
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler
import os
from dotenv import load_dotenv
import websocket
import json
import threading
import time

# Load biến môi trường
load_dotenv()

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Các thông tin cấu hình
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_USER_IDS = os.getenv("ADMIN_USER_IDS", "").split(",")
WEBSOCKET_SERVER = os.getenv("WEBSOCKET_SERVER", "localhost")
WEBSOCKET_PORT = os.getenv("WEBSOCKET_PORT", "7860")
WEBSOCKET_PATH = os.getenv("WEBSOCKET_PATH", "/notify")

# URL WebSocket
ws_url = f"ws://{WEBSOCKET_SERVER}:{WEBSOCKET_PORT}{WEBSOCKET_PATH}"

# Tham chiếu toàn cục đến application
app = None

# Lệnh bắt đầu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Xin chào! Tôi là Bot Admin. Tôi sẽ thông báo cho bạn khi có câu hỏi mới cần hỗ trợ.')

# Hàm gửi thông báo đến admin
async def send_notification_to_admin(message: str):
    if app:
        for admin_id in ADMIN_USER_IDS:
            try:
                await app.bot.send_message(chat_id=admin_id, text=message, parse_mode='HTML')
            except Exception as e:
                logging.error(f"Lỗi khi gửi thông báo đến admin {admin_id}: {e}")

# Xử lý tin nhắn từ WebSocket
def on_message(ws, message):
    try:
        data = json.loads(message)
        
        if data.get("type") == "new_session":
            session_data = data.get("data", {})
            user_question = session_data.get("message", "")
            user_name = session_data.get("first_name", "Người dùng không xác định")
            response = session_data.get("response", "")
            
            # Tạo thông báo
            notification = (
                f"⚠️ <b>Câu hỏi cần xử lý:</b>\n\n"
                f"<b>Từ:</b> {user_name}\n"
                f"<b>Câu hỏi:</b> {user_question}\n\n"
                f"<b>Trả lời hiện tại:</b> {response}\n\n"
                f"<i>Vui lòng trả lời người dùng này.</i>"
            )
            
            # Gửi thông báo (sử dụng asyncio để gọi hàm async từ hàm sync)
            import asyncio
            asyncio.run(send_notification_to_admin(notification))
            
    except json.JSONDecodeError:
        logging.error(f"Nhận tin nhắn không phải JSON: {message}")
    except Exception as e:
        logging.error(f"Lỗi xử lý tin nhắn: {e}")

# Các hàm WebSocket khác
def on_error(ws, error):
    logging.error(f"Lỗi WebSocket: {error}")

def on_close(ws, close_status_code, close_msg):
    logging.info(f"Kết nối WebSocket đã đóng: code={close_status_code}, message={close_msg}")

def on_open(ws):
    logging.info(f"Kết nối WebSocket đã mở tới {ws_url}")
    
    # Gửi keepalive định kỳ
    def send_keepalive():
        while True:
            try:
                if ws.sock and ws.sock.connected:
                    ws.send("keepalive")
                    logging.info("Đã gửi tin nhắn keepalive")
                time.sleep(300)  # 5 phút
            except Exception as e:
                logging.error(f"Lỗi khi gửi keepalive: {e}")
                time.sleep(60)
    
    keepalive_thread = threading.Thread(target=send_keepalive, daemon=True)
    keepalive_thread.start()

# Khởi tạo kết nối WebSocket
def start_websocket():
    def run_forever_with_reconnect():
        while True:
            try:
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                ws.run_forever(ping_interval=60, ping_timeout=30)
                logging.info("Kết nối WebSocket bị mất, kết nối lại sau 5 giây...")
                time.sleep(5)
            except Exception as e:
                logging.error(f"Lỗi kết nối WebSocket: {e}")
                time.sleep(5)
    
    websocket_thread = threading.Thread(target=run_forever_with_reconnect, daemon=True)
    websocket_thread.start()

# Hàm main
def main():
    global app
    
    # Khởi tạo ứng dụng Telegram Bot
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Đăng ký các handlers
    app.add_handler(CommandHandler("start", start))
    
    # Bắt đầu WebSocket client
    start_websocket()
    
    # Chạy bot
    app.run_polling()

if __name__ == '__main__':
    main()
```

## Lưu ý Quan Trọng

1. **Duy trì kết nối**: Gửi tin nhắn "keepalive" mỗi 5 phút để duy trì kết nối WebSocket.
2. **Xử lý mất kết nối**: Luôn triển khai cơ chế tự động kết nối lại khi mất kết nối.
3. **Bảo mật**: Nếu triển khai trong môi trường production, hãy sử dụng WSS (WebSocket Secure) thay vì WS.
4. **Giới hạn quyền**: Chỉ gửi thông báo đến các tài khoản Telegram được chỉ định làm admin.

## Cấu Hình Môi Trường

Đảm bảo các biến môi trường sau được thiết lập trong file `.env` của Admin Bot:

```
# Cấu hình Telegram Bot
TELEGRAM_TOKEN=your-telegram-bot-token
ADMIN_USER_IDS=123456789,987654321

# Cấu hình WebSocket
WEBSOCKET_SERVER=backend.example.com
WEBSOCKET_PORT=443
WEBSOCKET_PATH=/notify
```

## Kiểm Tra Kết Nối

Để kiểm tra kết nối WebSocket đã hoạt động, bạn có thể:

1. Chạy Admin Bot và kiểm tra log xem kết nối đã được thiết lập chưa
2. Gửi một câu hỏi đến hệ thống mà bạn biết hệ thống sẽ trả lời "I don't know..."
3. Kiểm tra xem Admin Bot có nhận được thông báo không

## Xử Lý Sự Cố

Nếu gặp vấn đề với kết nối WebSocket, hãy kiểm tra:

1. URL WebSocket đã chính xác và có thể truy cập được không
2. Cổng WebSocket đã được mở trong tường lửa chưa
3. Kiểm tra log của cả Backend và Admin Bot để phát hiện lỗi
4. Đảm bảo tất cả các thư viện được yêu cầu đã được cài đặt (`pip install websocket-client python-telegram-bot python-dotenv`) 