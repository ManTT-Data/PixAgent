# PIX Project Backend

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python 3.10](https://img.shields.io/badge/Python-3.10-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![HuggingFace Spaces](https://img.shields.io/badge/HuggingFace-Spaces-yellow?style=flat&logo=huggingface&logoColor=white)](https://huggingface.co/spaces)

Backend API for PIX Project with MongoDB, PostgreSQL and RAG integration. This project provides a comprehensive backend solution for managing FAQ items, emergency contacts, events, and a RAG-based question answering system.

## Features

- **MongoDB Integration**: Store user sessions and conversation history
- **PostgreSQL Integration**: Manage FAQ items, emergency contacts, and events
- **Pinecone Vector Database**: Store and retrieve vector embeddings for RAG
- **RAG Question Answering**: Answer questions using relevant information from the vector database
- **API Documentation**: Automatic Swagger documentation
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
- (And more PostgreSQL endpoints for documents, vector databases, etc.)

### RAG Endpoints

- `POST /rag/chat`: Get answer for a question using RAG
- `POST /rag/embedding`: Generate embedding for text
- `GET /rag/health`: Check RAG services health

### Debug Endpoints (Available in Debug Mode Only)

- `GET /debug/config`: Get configuration information
- `GET /debug/system`: Get system information (CPU, memory, disk usage)
- `GET /debug/database`: Check all database connections
- `GET /debug/errors`: View recent error logs
- `GET /debug/performance`: Get performance metrics
- `GET /debug/full`: Get comprehensive debug information

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

# Application settings
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO
```

## Auto-Debugging Features

The project includes built-in debugging tools to help diagnose and fix issues:

- **Error Tracking**: Automatic logging and tracking of exceptions
- **Performance Monitoring**: Tracking of execution time for critical operations
- **Database Health Checks**: Automatic validation of database connections
- **System Monitoring**: Tracking system resources like CPU, memory, and disk usage
- **Request Logging**: Comprehensive logging of all API requests and responses

To enable debug mode, set `DEBUG=true` in your `.env` file. This will enable:
- All debug endpoints
- Automatic table creation
- More verbose logging
- Enhanced error responses

## Installation and Setup

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/pix-project-backend.git
   cd pix-project-backend
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
   uvicorn main:app --reload
   ```

5. Open your browser and navigate to [http://localhost:8000/docs](http://localhost:8000/docs) to see the API documentation

### Docker Deployment

1. Build the Docker image:
   ```bash
   docker build -t pix-project-backend .
   ```

2. Run the Docker container:
   ```bash
   docker run -p 8000:8000 --env-file .env pix-project-backend
   ```

## Deployment to HuggingFace Spaces

1. Create a new Space on HuggingFace (Dockerfile type)
2. Link your GitHub repository or push directly to the HuggingFace repo
3. Add your environment variables in the Space settings
4. Deploy and enjoy!

## Project Structure

```
.
├── app
│   ├── api
│   │   ├── mongodb_routes.py
│   │   ├── postgresql_routes.py
│   │   └── rag_routes.py
│   ├── database
│   │   ├── models.py
│   │   ├── mongodb.py
│   │   ├── pinecone.py
│   │   └── postgresql.py
│   ├── models
│   │   ├── mongodb_models.py
│   │   └── rag_models.py
│   └── utils
│       ├── middleware.py
│       ├── debug_utils.py
│       └── utils.py
├── .env
├── .env.example
├── .gitignore
├── Dockerfile
├── README.md
├── create_tables.py
├── main.py
└── requirements.txt
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 