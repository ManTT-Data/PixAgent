# API Documentation

## Frontend Setup

```javascript
// Basic Axios setup
import axios from 'axios';

const api = axios.create({
  baseURL: 'https://api.your-domain.com',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  }
});

// Error handling
api.interceptors.response.use(
  response => response.data,
  error => {
    const errorMessage = error.response?.data?.detail || 'An error occurred';
    console.error('API Error:', errorMessage);
    return Promise.reject(errorMessage);
  }
);
```

## Caching System

- All GET endpoints support `use_cache=true` parameter (default)
- Cache TTL: 300 seconds (5 minutes)
- Cache is automatically invalidated on data changes

## Authentication

Currently no authentication is required. If implemented in the future, use JWT Bearer tokens:

```javascript
const api = axios.create({
  // ...other config
  headers: {
    // ...other headers
    'Authorization': `Bearer ${token}`
  }
});
```

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request |
| 404 | Not Found |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

## PostgreSQL Endpoints

### FAQ Endpoints

#### Get FAQs List
```
GET /postgres/faq
```

Parameters:
- `skip`: Number of items to skip (default: 0)
- `limit`: Maximum items to return (default: 100)
- `active_only`: Return only active items (default: false)
- `use_cache`: Use cached data if available (default: true)

Response:
```json
[
  {
    "question": "How do I book a hotel?",
    "answer": "You can book a hotel through our app or website.",
    "is_active": true,
    "id": 1,
    "created_at": "2023-01-01T00:00:00",
    "updated_at": "2023-01-01T00:00:00"
  }
]
```

Example:
```javascript
async function getFAQs() {
  try {
    const data = await api.get('/postgres/faq', {
      params: { active_only: true, limit: 20 }
    });
    return data;
  } catch (error) {
    console.error('Error fetching FAQs:', error);
    throw error;
  }
}
```

#### Create FAQ
```
POST /postgres/faq
```

Request Body:
```json
{
  "question": "How do I book a hotel?",
  "answer": "You can book a hotel through our app or website.",
  "is_active": true
}
```

Response: Created FAQ object

#### Get FAQ Detail
```
GET /postgres/faq/{faq_id}
```

Parameters:
- `faq_id`: ID of FAQ (required)
- `use_cache`: Use cached data if available (default: true)

Response: FAQ object

#### Update FAQ
```
PUT /postgres/faq/{faq_id}
```

Parameters:
- `faq_id`: ID of FAQ to update (required)

Request Body: Partial or complete FAQ object
Response: Updated FAQ object

#### Delete FAQ
```
DELETE /postgres/faq/{faq_id}
```

Parameters:
- `faq_id`: ID of FAQ to delete (required)

Response:
```json
{
  "status": "success",
  "message": "FAQ item 1 deleted"
}
```

#### Batch Operations

Create multiple FAQs:
```
POST /postgres/faqs/batch
```

Update status of multiple FAQs:
```
PUT /postgres/faqs/batch-update-status
```

Delete multiple FAQs:
```
DELETE /postgres/faqs/batch
```

### Emergency Contact Endpoints

#### Get Emergency Contacts
```
GET /postgres/emergency
```

Parameters:
- `skip`: Number of items to skip (default: 0)
- `limit`: Maximum items to return (default: 100)
- `active_only`: Return only active items (default: false)
- `use_cache`: Use cached data if available (default: true)

Response: Array of Emergency Contact objects

#### Create Emergency Contact
```
POST /postgres/emergency
```

Request Body:
```json
{
  "name": "Fire Department",
  "phone_number": "114",
  "description": "Fire rescue services",
  "address": "Da Nang",
  "location": "16.0544, 108.2022",
  "priority": 1,
  "is_active": true
}
```

Response: Created Emergency Contact object

#### Get Emergency Contact
```
GET /postgres/emergency/{emergency_id}
```

#### Update Emergency Contact
```
PUT /postgres/emergency/{emergency_id}
```

#### Delete Emergency Contact
```
DELETE /postgres/emergency/{emergency_id}
```

#### Batch Operations

Create multiple Emergency Contacts:
```
POST /postgres/emergency/batch
```

Update status of multiple Emergency Contacts:
```
PUT /postgres/emergency/batch-update-status
```

Delete multiple Emergency Contacts:
```
DELETE /postgres/emergency/batch
```

### Event Endpoints

#### Get Events
```
GET /postgres/events
```

Parameters:
- `skip`: Number of items to skip (default: 0)
- `limit`: Maximum items to return (default: 100)
- `active_only`: Return only active items (default: false)
- `featured_only`: Return only featured items (default: false)
- `use_cache`: Use cached data if available (default: true)

Response: Array of Event objects

#### Create Event
```
POST /postgres/events
```

Request Body:
```json
{
  "name": "Da Nang Fireworks Festival",
  "description": "International Fireworks Festival Da Nang 2023",
  "address": "Dragon Bridge, Da Nang",
  "location": "16.0610, 108.2277",
  "date_start": "2023-06-01T19:00:00",
  "date_end": "2023-06-01T22:00:00",
  "price": [
    {"type": "VIP", "amount": 500000},
    {"type": "Standard", "amount": 300000}
  ],
  "url": "https://danangfireworks.com",
  "is_active": true,
  "featured": true
}
```

Response: Created Event object

#### Get Event
```
GET /postgres/events/{event_id}
```

#### Update Event
```
PUT /postgres/events/{event_id}
```

#### Delete Event
```
DELETE /postgres/events/{event_id}
```

#### Batch Operations

Create multiple Events:
```
POST /postgres/events/batch
```

Update status of multiple Events:
```
PUT /postgres/events/batch-update-status
```

Delete multiple Events:
```
DELETE /postgres/events/batch
```

### About Pixity Endpoints

#### Get About Pixity
```
GET /postgres/about-pixity
```

Response:
```json
{
  "content": "PiXity is your smart, AI-powered local companion...",
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

#### Update About Pixity
```
PUT /postgres/about-pixity
```

Request Body:
```json
{
  "content": "PiXity is your smart, AI-powered local companion..."
}
```

Response: Updated About Pixity object

### Da Nang Bucket List Endpoints

#### Get Da Nang Bucket List
```
GET /postgres/danang-bucket-list
```

Response: Bucket List object with JSON content string

#### Update Da Nang Bucket List
```
PUT /postgres/danang-bucket-list
```

### Solana Summit Endpoints

#### Get Solana Summit
```
GET /postgres/solana-summit
```

Response: Solana Summit object with JSON content string

#### Update Solana Summit
```
PUT /postgres/solana-summit
```

### Health Check
```
GET /postgres/health
```

Response:
```json
{
  "status": "healthy",
  "message": "PostgreSQL connection is working",
  "timestamp": "2023-01-01T00:00:00"
}
```

## MongoDB Endpoints

### Session Endpoints

#### Create Session
```
POST /session
```

Request Body:
```json
{
  "user_id": "user123",
  "query": "How do I book a room?",
  "timestamp": "2023-01-01T00:00:00",
  "metadata": {
    "client_info": "web",
    "location": "Da Nang"
  }
}
```

Response: Created Session object with session_id

#### Update Session with Response
```
PUT /session/{session_id}/response
```

Request Body:
```json
{
  "response": "You can book a room through our app or website.",
  "response_timestamp": "2023-01-01T00:00:05",
  "metadata": {
    "response_time_ms": 234,
    "model_version": "gpt-4"
  }
}
```

Response: Updated Session object

#### Get Session
```
GET /session/{session_id}
```

Response: Session object

#### Get User History
```
GET /history
```

Parameters:
- `user_id`: User ID (required)
- `limit`: Maximum sessions to return (default: 10)
- `skip`: Number of sessions to skip (default: 0)

Response:
```json
{
  "user_id": "user123",
  "sessions": [
    {
      "session_id": "60f7a8b9c1d2e3f4a5b6c7d8",
      "query": "How do I book a room?",
      "timestamp": "2023-01-01T00:00:00",
      "response": "You can book a room through our app or website.",
      "response_timestamp": "2023-01-01T00:00:05"
    }
  ],
  "total_count": 1
}
```

#### Health Check
```
GET /health
```

## RAG Endpoints

### Create Embedding
```
POST /embedding
```

Request Body:
```json
{
  "text": "Text to embed"
}
```

Response:
```json
{
  "embedding": [0.1, 0.2, 0.3, ...],
  "dimensions": 1536
}
```

### Process Chat Request
```
POST /chat
```

Request Body:
```json
{
  "query": "Can you tell me about Pixity?",
  "chat_history": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hello! How can I help you?"}
  ]
}
```

Response:
```json
{
  "answer": "Pixity is a platform...",
  "sources": [
    {
      "document_id": "doc123",
      "chunk_id": "chunk456",
      "chunk_text": "Pixity was founded in...",
      "relevance_score": 0.92
    }
  ]
}
```

### Direct RAG Query
```
POST /rag
```

Request Body:
```json
{
  "query": "Can you tell me about Pixity?",
  "namespace": "about_pixity",
  "top_k": 3
}
```

Response: Query results with relevance scores

### Health Check
```
GET /health
```

## PDF Processing Endpoints

### Upload and Process PDF
```
POST /pdf/upload
```

Form Data:
- `file`: PDF file (required)
- `namespace`: Vector database namespace (default: "Default")
- `index_name`: Vector database index name (default: "testbot768")
- `title`: Document title (optional)
- `description`: Document description (optional)
- `user_id`: User ID for WebSocket updates (optional)

Response: Processing results with document_id

### Delete Documents in Namespace
```
DELETE /pdf/namespace
```

Parameters:
- `namespace`: Vector database namespace (default: "Default")
- `index_name`: Vector database index name (default: "testbot768")
- `user_id`: User ID for WebSocket updates (optional)

Response: Deletion results

### Get Documents List
```
GET /pdf/documents
```

Parameters:
- `namespace`: Vector database namespace (default: "Default")
- `index_name`: Vector database index name (default: "testbot768")

Response: List of documents in the namespace 