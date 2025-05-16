---
title: PIX Project Backend
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: docker
sdk_version: "3.0.0"
app_file: app.py
pinned: false
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference

# PIX Project Backend

[![FastAPI](https://img.shields.io/badge/FastAPI-0.103.1-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![HuggingFace Spaces](https://img.shields.io/badge/HuggingFace-Spaces-yellow?style=flat&logo=huggingface&logoColor=white)](https://huggingface.co/spaces)

Backend API for PIX Project with MongoDB, PostgreSQL and RAG integration. This project provides a comprehensive backend solution for managing FAQ items, emergency contacts, events, and a RAG-based question answering system.

## Features

- **MongoDB Integration**: Store user sessions and conversation history
- **PostgreSQL Integration**: Manage FAQ items, emergency contacts, and events
- **Pinecone Vector Database**: Store and retrieve vector embeddings for RAG
- **RAG Question Answering**: Answer questions using relevant information from the vector database
- **WebSocket Notifications**: Real-time notifications for Admin Bot
- **API Documentation**: Automatic OpenAPI documentation via Swagger
- **Docker Support**: Easy deployment using Docker
- **Auto-Debugging**: Built-in debugging, error tracking, and performance monitoring

## API Endpoints

### MongoDB Endpoints

- `POST /mongodb/session`: Create a new session record
- `PUT /mongodb/session/{session_id}/response`: Update a session with a response
- `GET /mongodb/history`: Get user conversation history
- `GET /mongodb/health`: Check MongoDB connection health

### PostgreSQL Endpoints

- `GET /postgres/health`: Check PostgreSQL connection health
- `GET /postgres/faq`: Get FAQ items
- `POST /postgres/faq`: Create a new FAQ item
- `GET /postgres/faq/{faq_id}`: Get a specific FAQ item
- `PUT /postgres/faq/{faq_id}`: Update a specific FAQ item
- `DELETE /postgres/faq/{faq_id}`: Delete a specific FAQ item
- `GET /postgres/emergency`: Get emergency contact items
- `POST /postgres/emergency`: Create a new emergency contact item
- `GET /postgres/emergency/{emergency_id}`: Get a specific emergency contact
- `GET /postgres/events`: Get event items

### RAG Endpoints

- `POST /rag/chat`: Get answer for a question using RAG
- `POST /rag/embedding`: Generate embedding for text
- `GET /rag/health`: Check RAG services health

### WebSocket Endpoints

- `WebSocket /notify`: Receive real-time notifications for new sessions

### Debug Endpoints (Available in Debug Mode Only)

- `GET /debug/config`: Get configuration information
- `GET /debug/system`: Get system information (CPU, memory, disk usage)
- `GET /debug/database`: Check all database connections
- `GET /debug/errors`: View recent error logs
- `GET /debug/performance`: Get performance metrics
- `GET /debug/full`: Get comprehensive debug information

## WebSocket API

### Notifications for New Sessions

The backend provides a WebSocket endpoint for receiving notifications about new sessions that match specific criteria.

#### WebSocket Endpoint Configuration

The WebSocket endpoint is configured using environment variables:

```
# WebSocket configuration
WEBSOCKET_SERVER=localhost
WEBSOCKET_PORT=7860
WEBSOCKET_PATH=/notify
```

The full WebSocket URL will be:
```
ws://{WEBSOCKET_SERVER}:{WEBSOCKET_PORT}{WEBSOCKET_PATH}
```

For example: `ws://localhost:7860/notify`

#### Notification Criteria

A notification is sent when:
1. A new session is created with `factor` set to "RAG"
2. The message content starts with "I don't know"

#### Notification Format

```json
{
  "type": "new_session",
  "timestamp": "2025-04-15 22:30:45",
  "data": {
    "session_id": "123e4567-e89b-12d3-a456-426614174000",
    "factor": "rag",
    "action": "asking_freely",
    "created_at": "2025-04-15 22:30:45",
    "first_name": "John",
    "last_name": "Doe",
    "message": "I don't know how to find emergency contacts",
    "user_id": "12345678",
    "username": "johndoe"
  }
}
```

#### Usage Example

Admin Bot should establish a WebSocket connection to this endpoint using the configured URL:

```python
import websocket
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get WebSocket configuration from environment variables
WEBSOCKET_SERVER = os.getenv("WEBSOCKET_SERVER", "localhost")
WEBSOCKET_PORT = os.getenv("WEBSOCKET_PORT", "7860")
WEBSOCKET_PATH = os.getenv("WEBSOCKET_PATH", "/notify")

# Create full URL
ws_url = f"ws://{WEBSOCKET_SERVER}:{WEBSOCKET_PORT}{WEBSOCKET_PATH}"

def on_message(ws, message):
    data = json.loads(message)
    print(f"Received notification: {data}")
    # Forward to Telegram Admin

def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("Connection closed")

def on_open(ws):
    print("Connection opened")
    # Send keepalive message periodically
    ws.send("keepalive")

# Connect to WebSocket
ws = websocket.WebSocketApp(
    ws_url,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)
ws.run_forever()
```

When a notification is received, Admin Bot should forward the content to the Telegram Admin.

## Environment Variables

Create a `.env` file with the following variables:

```
# PostgreSQL Configuration
DB_CONNECTION_MODE=aiven
AIVEN_DB_URL=postgresql://username:password@host:port/dbname?sslmode=require

# MongoDB Configuration
MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
DB_NAME=Telegram
COLLECTION_NAME=session_chat

# Pinecone configuration
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX_NAME=your-pinecone-index-name
PINECONE_ENVIRONMENT=gcp-starter

# Google Gemini API key
GOOGLE_API_KEY=your-google-api-key

# WebSocket configuration
WEBSOCKET_SERVER=localhost
WEBSOCKET_PORT=7860
WEBSOCKET_PATH=/notify

# Application settings
ENVIRONMENT=production
DEBUG=false
PORT=7860
```

## Installation and Setup

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/ManTT-Data/PixAgent.git
   cd PixAgent
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your configuration (see above)

4. Run the application:
   ```bash
   uvicorn app:app --reload --port 7860
   ```

5. Open your browser and navigate to [http://localhost:7860/docs](http://localhost:7860/docs) to see the API documentation

### Docker Deployment

1. Build the Docker image:
   ```bash
   docker build -t pix-project-backend .
   ```

2. Run the Docker container:
   ```bash
   docker run -p 7860:7860 --env-file .env pix-project-backend
   ```

## Deployment to HuggingFace Spaces

1. Create a new Space on HuggingFace (Dockerfile type)
2. Link your GitHub repository or push directly to the HuggingFace repo
3. Add your environment variables in the Space settings
4. The deployment will use `app.py` as the entry point, which is the standard for HuggingFace Spaces

### Important Notes for HuggingFace Deployment

- The application uses `app.py` with the FastAPI instance named `app` to avoid the "Error loading ASGI app. Attribute 'app' not found in module 'app'" error
- Make sure all environment variables are set in the Space settings
- The Dockerfile is configured to expose port 7860, which is the default port for HuggingFace Spaces

## Project Structure

```
.
├── app                  # Main application package
│   ├── api              # API endpoints
│   │   ├── mongodb_routes.py
│   │   ├── postgresql_routes.py
│   │   ├── rag_routes.py
│   │   └── websocket_routes.py
│   ├── database         # Database connections
│   │   ├── mongodb.py
│   │   ├── pinecone.py
│   │   └── postgresql.py
│   ├── models           # Pydantic models
│   │   ├── mongodb_models.py
│   │   ├── postgresql_models.py
│   │   └── rag_models.py
│   └── utils            # Utility functions
│       ├── debug_utils.py
│       └── middleware.py
├── tests                # Test directory
│   └── test_api_endpoints.py
├── .dockerignore        # Docker ignore file
├── .env.example         # Example environment file
├── .gitattributes       # Git attributes
├── .gitignore           # Git ignore file
├── app.py               # Application entry point
├── docker-compose.yml   # Docker compose configuration
├── Dockerfile           # Docker configuration
├── pytest.ini           # Pytest configuration
├── README.md            # Project documentation
├── requirements.txt     # Project dependencies
└── api_documentation.txt # API documentation for frontend engineers
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

# Advanced Retrieval System

This project now features an enhanced vector retrieval system that improves the quality and relevance of information retrieved from Pinecone using threshold-based filtering and multiple similarity metrics.

## Features

### 1. Threshold-Based Retrieval

The system implements a threshold-based approach to vector retrieval, which:
- Retrieves a larger candidate set from the vector database
- Applies a similarity threshold to filter out less relevant results
- Returns only the most relevant documents that exceed the threshold

### 2. Multiple Similarity Metrics

The system supports multiple similarity metrics:
- **Cosine Similarity** (default): Measures the cosine of the angle between vectors
- **Dot Product**: Calculates the dot product between vectors
- **Euclidean Distance**: Measures the straight-line distance between vectors

Each metric has different characteristics and may perform better for different types of data and queries.

### 3. Score Normalization

For metrics like Euclidean distance where lower values indicate higher similarity, the system automatically normalizes scores to a 0-1 scale where higher values always indicate higher similarity. This makes it easier to compare results across different metrics.

## Configuration

The retrieval system can be configured through environment variables:

```
# Pinecone retrieval configuration
PINECONE_DEFAULT_LIMIT_K=10       # Maximum number of candidates to retrieve
PINECONE_DEFAULT_TOP_K=6          # Number of results to return after filtering
PINECONE_DEFAULT_SIMILARITY_METRIC=cosine  # Default similarity metric
PINECONE_DEFAULT_SIMILARITY_THRESHOLD=0.75 # Similarity threshold (0-1)
PINECONE_ALLOWED_METRICS=cosine,dotproduct,euclidean  # Available metrics
```

## API Usage

You can customize the retrieval parameters when making API requests:

```json
{
  "user_id": "user123",
  "question": "What are the best restaurants in Da Nang?",
  "similarity_top_k": 5,
  "limit_k": 15,
  "similarity_metric": "cosine",
  "similarity_threshold": 0.8
}
```

## Benefits

1. **Quality Improvement**: Retrieves only the most relevant documents above a certain quality threshold
2. **Flexibility**: Different similarity metrics can be used for different types of queries
3. **Efficiency**: Avoids processing irrelevant documents, improving response time
4. **Configurability**: All parameters can be adjusted via environment variables or at request time

## Implementation Details

The system is implemented as a custom retriever class `ThresholdRetriever` that integrates with LangChain's retrieval infrastructure while providing enhanced functionality.

## In-Memory Cache

Dự án bao gồm một hệ thống cache trong bộ nhớ để giảm thiểu truy cập đến cơ sở dữ liệu PostgreSQL và MongoDB.

### Cấu hình Cache

Cache được cấu hình thông qua các biến môi trường:

```
# Cache Configuration
CACHE_TTL_SECONDS=300           # Thời gian tồn tại của cache item (giây)
CACHE_CLEANUP_INTERVAL=60       # Chu kỳ xóa cache hết hạn (giây)
CACHE_MAX_SIZE=1000             # Số lượng item tối đa trong cache
HISTORY_QUEUE_SIZE=10           # Số lượng item tối đa trong queue lịch sử người dùng
HISTORY_CACHE_TTL=3600          # Thời gian tồn tại của lịch sử người dùng (giây)
```

### Cơ chế Cache

Hệ thống cache kết hợp hai cơ chế hết hạn:

1. **Lazy Expiration**: Kiểm tra thời hạn khi truy cập cache item. Nếu item đã hết hạn, nó sẽ bị xóa và trả về kết quả là không tìm thấy.

2. **Active Expiration**: Một background thread định kỳ quét và xóa các item đã hết hạn. Điều này giúp tránh tình trạng cache quá lớn với các item không còn được sử dụng.

### Các loại dữ liệu được cache

- **Dữ liệu PostgreSQL**: Thông tin từ các bảng FAQ, Emergency Contacts, và Events.
- **Lịch sử người dùng từ MongoDB**: Lịch sử hội thoại người dùng được lưu trong queue với thời gian sống tính theo lần truy cập cuối cùng.

### API Cache

Dự án cung cấp các API endpoints để quản lý cache:

- `GET /cache/stats`: Xem thống kê về cache (tổng số item, bộ nhớ sử dụng, v.v.)
- `DELETE /cache/clear`: Xóa toàn bộ cache
- `GET /debug/cache`: (Chỉ trong chế độ debug) Xem thông tin chi tiết về cache, bao gồm các keys và cấu hình

### Cách hoạt động

1. Khi một request đến, hệ thống sẽ kiểm tra dữ liệu trong cache trước.
2. Nếu dữ liệu tồn tại và còn hạn, trả về từ cache.
3. Nếu dữ liệu không tồn tại hoặc đã hết hạn, truy vấn từ database và lưu kết quả vào cache.
4. Khi dữ liệu được cập nhật hoặc xóa, cache liên quan sẽ tự động được xóa.

### Lịch sử người dùng

Lịch sử hội thoại người dùng được lưu trong queue riêng với cơ chế đặc biệt:

- Mỗi người dùng có một queue riêng với kích thước giới hạn (`HISTORY_QUEUE_SIZE`).
- Thời gian sống của queue được làm mới mỗi khi có tương tác mới.
- Khi queue đầy, các item cũ nhất sẽ bị loại bỏ.
- Queue tự động bị xóa sau một thời gian không hoạt động.

## Tác giả

- **PIX Project Team**

# PixAgent PDF Processing

This README provides instructions for the PDF processing functionality in PixAgent, including uploading PDF documents, managing vector embeddings, and deleting documents.

## API Endpoints

### Health Check

```
GET /health
GET /pdf/health
```

Verify the API is running and the connection to databases (MongoDB, PostgreSQL, Pinecone) is established.

### Upload PDF

```
POST /pdf/upload
```

**Parameters:**
- `file`: The PDF file to upload (multipart/form-data)
- `namespace`: The namespace to store vectors in (default: "Default")
- `mock_mode`: Set to "true" or "false" (default: "false")
- `vector_database_id`: The ID of the vector database to use (required for real mode)
- `document_id`: Optional custom document ID (if not provided, a UUID will be generated)

**Example Python Request:**
```python
import requests
import uuid

document_id = str(uuid.uuid4())
files = {'file': open('your_document.pdf', 'rb')}
response = requests.post(
    'http://localhost:8000/pdf/upload',
    files=files,
    data={
        'namespace': 'my-namespace',
        'mock_mode': 'false',
        'vector_database_id': '9',
        'document_id': document_id
    }
)
print(f'Status: {response.status_code}')
print(f'Response: {response.json()}')
```

### List Documents

```
GET /pdf/documents
```

**Parameters:**
- `namespace`: The namespace to retrieve documents from
- `vector_database_id`: The ID of the vector database to use

**Example Python Request:**
```python
import requests

response = requests.get(
    'http://localhost:8000/pdf/documents',
    params={
        'namespace': 'my-namespace',
        'vector_database_id': '9'
    }
)
print(f'Status: {response.status_code}')
print(f'Documents: {response.json()}')
```

### Delete Document

```
DELETE /pdf/document
```

**Parameters:**
- `document_id`: The ID of the document to delete
- `namespace`: The namespace containing the document
- `vector_database_id`: The ID of the vector database

**Example Python Request:**
```python
import requests

response = requests.delete(
    'http://localhost:8000/pdf/document',
    params={
        'document_id': 'your-document-id',
        'namespace': 'my-namespace',
        'vector_database_id': '9'
    }
)
print(f'Status: {response.status_code}')
print(f'Result: {response.json()}')
```

### List Available Vector Databases

```
GET /postgres/vector-databases
```

**Example Python Request:**
```python
import requests

response = requests.get('http://localhost:8000/postgres/vector-databases')
vector_dbs = response.json()
print(f'Available vector databases: {vector_dbs}')
```

## PDF Processing and Vector Embedding

The system processes PDFs in the following steps:

1. **Text Extraction**: Uses `PyPDFLoader` from LangChain to extract text from the PDF.
2. **Text Chunking**: Splits the text into manageable chunks using `RecursiveCharacterTextSplitter` with a chunk size of 1000 characters and 100 character overlap.
3. **Embedding Creation**: Uses Google's Gemini embedding model (`models/embedding-001`) to create embeddings for each text chunk.
4. **Dimension Adjustment**: Ensures the embedding dimensions match the Pinecone index requirements:
   - If Gemini produces 768-dim embeddings and Pinecone expects 1536-dim, each value is duplicated.
   - For other mismatches, appropriate padding or truncation is applied.
5. **Vector Storage**: Uploads the embeddings to Pinecone in the specified namespace.

## Notes

- **Mock Mode**: When `mock_mode` is set to "true", the system simulates the PDF processing without actually creating or storing embeddings.
- **Namespace Handling**: When using a vector database ID, the namespace is automatically formatted as `vdb-{vector_database_id}`.
- **Error Handling**: The system validates vector dimensions and handles errors appropriately, with detailed logging.
- **PDF Storage**: Processed PDFs are stored in the `pdf_storage` directory with the document ID as the filename.

## Troubleshooting

- **Dimension Mismatch Error**: If you receive an error about vector dimensions not matching Pinecone index configuration, check that the embedding model and Pinecone index dimensions are compatible. The system will attempt to adjust dimensions but may encounter limits.
- **Connection Issues**: Verify that MongoDB, PostgreSQL, and Pinecone credentials are correctly configured in the environment variables.
- **Processing Failures**: Check the `pdf_api_debug.log` file for detailed error messages and processing information. 
