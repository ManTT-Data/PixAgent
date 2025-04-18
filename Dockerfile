# 1. Base image
FROM python:3.11-slim

# 2. Set up working directory
WORKDIR /app

# 3. Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy all code
COPY . .

# 5. Expose (not required, but for clarity)
EXPOSE $PORT

# 6. Startup command using PORT variable from Render
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
