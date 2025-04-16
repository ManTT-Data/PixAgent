FROM python:3.11-slim

WORKDIR /app

# Cài đặt các gói hệ thống cần thiết
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Sao chép các file yêu cầu trước để tận dụng cache của Docker
COPY requirements.txt .

# Cài đặt các gói Python
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ code vào container
COPY . .

# Mở cổng mà ứng dụng sẽ chạy
EXPOSE 7860

# Chạy ứng dụng với uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"] 