# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy và cài dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ source
COPY . .

# Expose port (metadata, không quan trọng với $PORT)
EXPOSE 7860

# Start bằng uvicorn, dùng biến PORT nếu có
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
