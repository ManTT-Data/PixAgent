# 1. Base image
FROM python:3.11-slim

# 2. Thiết lập working dir
WORKDIR /app

# 3. Copy requirements và cài
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy toàn bộ code
COPY . .

# 5. Expose (không bắt buộc, nhưng rõ ràng)
EXPOSE  $PORT

# 6. Lệnh khởi động sử dụng biến PORT từ Render
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
