from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, Request
from typing import List, Optional, Dict, Any
import logging
import time
import os
import json
import hashlib
import asyncio
import traceback
import google.generativeai as genai
from datetime import datetime
from langchain.prompts import PromptTemplate
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.utils.utils import cache, timer_decorator

from app.database.mongodb import get_user_history, get_chat_history, get_request_history, save_session, session_collection
from app.database.pinecone import (
    search_vectors, 
    get_chain, 
)
from app.models.rag_models import (
    ChatRequest,
    ChatResponse,
    ChatResponseInternal,
    SourceDocument,
    EmbeddingRequest,
    EmbeddingResponse,
    UserMessageModel
)

# Sử dụng bộ nhớ đệm thay vì Redis
class SimpleCache:
    def __init__(self):
        self.cache = {}
        self.expiration = {}
    
    async def get(self, key):
        if key in self.cache:
            # Kiểm tra xem cache đã hết hạn chưa
            if key in self.expiration and self.expiration[key] > time.time():
                return self.cache[key]
            else:
                # Xóa cache đã hết hạn
                if key in self.cache:
                    del self.cache[key]
                if key in self.expiration:
                    del self.expiration[key]
        return None
    
    async def set(self, key, value, ex=300):  # Mặc định 5 phút
        self.cache[key] = value
        self.expiration[key] = time.time() + ex

# Khởi tạo SimpleCache
redis_client = SimpleCache()

# Configure logging
logger = logging.getLogger(__name__)

# Configure Google Gemini API
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# Create router
router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
)

# Create a prompt template with conversation history
prompt = PromptTemplate(
    template = """Goal:
You are a professional tour guide assistant that assists users in finding information about places in Da Nang, Vietnam.
You can provide details on restaurants, cafes, hotels, attractions, and other local venues. 
You have to use core knowledge and conversation history to chat with users, who are Da Nang's tourists. 

Return Format:
Respond in friendly, natural, concise and use only English like a real tour guide.
Always use HTML tags (e.g. <b> for bold) so that Telegram can render the special formatting correctly.

Warning:
Let's support users like a real tour guide, not a bot. The information in core knowledge is your own knowledge.
Your knowledge is provided in the Core Knowledge. All of information in Core Knowledge is about Da Nang, Vietnam.
You just care about current time that user mention when user ask about Solana event.
If you do not have enough information to answer user's question, please reply with "I don't know. I don't have information about that".

Core knowledge:
{context}

Conversation History:
{chat_history}

User message:
{question}

Your message:
""",
    input_variables = ["context", "question", "chat_history"],
)

# Helper for embeddings
async def get_embedding(text: str):
    """Get embedding from Google Gemini API"""
    try:
        # Initialize embedding model
        embedding_model = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        
        # Generate embedding
        result = await embedding_model.aembed_query(text)
        
        # Return embedding
        return {
            "embedding": result,
            "text": text,
            "model": "embedding-001"
        }
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate embedding: {str(e)}")

# Endpoint for generating embeddings
@router.post("/embedding", response_model=EmbeddingResponse)
async def create_embedding(request: EmbeddingRequest):
    """
    Generate embedding for text.
    
    - **text**: Text to generate embedding for
    """
    try:
        # Get embedding
        embedding_data = await get_embedding(request.text)
        
        # Return embedding
        return EmbeddingResponse(**embedding_data)
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate embedding: {str(e)}")

@timer_decorator
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Get answer for a question using RAG.
    
    - **user_id**: User's ID from Telegram
    - **question**: User's question
    - **include_history**: Whether to include user history in prompt (default: True)
    - **use_rag**: Whether to use RAG (default: True)
    - **similarity_top_k**: Number of top similar documents to retrieve (default: 3)
    - **vector_distance_threshold**: Threshold for vector similarity (default: 0.75)
    - **session_id**: Optional session ID for tracking conversations
    - **first_name**: User's first name
    - **last_name**: User's last name
    - **username**: User's username
    """
    start_time = time.time()
    try:
        # Create cache key for request
        cache_key = f"rag_chat:{request.user_id}:{request.question}:{request.include_history}:{request.use_rag}"
        
        # Check cache using redis_client instead of cache
        cached_response = await redis_client.get(cache_key)
        if cached_response is not None:
            logger.info(f"Cache hit for RAG chat request from user {request.user_id}")
            try:
                # If cached_response is string (JSON), parse it
                if isinstance(cached_response, str):
                    cached_data = json.loads(cached_response)
                    return ChatResponse(
                        answer=cached_data.get("answer", ""),
                        processing_time=cached_data.get("processing_time", 0.0)
                    )
                # If cached_response is object with sources, extract answer and processing_time
                elif hasattr(cached_response, 'sources'):
                    return ChatResponse(
                        answer=cached_response.answer,
                        processing_time=cached_response.processing_time
                    )
                # Otherwise, return cached response as is
                return cached_response
            except Exception as e:
                logger.error(f"Error parsing cached response: {e}")
                # Continue processing if cache parsing fails
        
        # Save user message first (so it's available for user history)
        session_id = request.session_id or f"{request.user_id}_{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}"
        logger.info(f"Processing chat request for user {request.user_id}, session {session_id}")
        
        # First, save the user's message so it's available for history lookups
        try:
            # Save user's question
            save_session(
                session_id=session_id,
                factor="user",
                action="asking_freely",
                first_name=getattr(request, 'first_name', "User"),
                last_name=getattr(request, 'last_name', ""),
                message=request.question,
                user_id=request.user_id,
                username=getattr(request, 'username', ""),
                response=None  # No response yet
            )
            logger.info(f"User message saved for session {session_id}")
        except Exception as e:
            logger.error(f"Error saving user message to session: {e}")
            # Continue processing even if saving fails
        
        # Use the RAG pipeline
        if request.use_rag:
            # Get the retriever
            retriever = get_chain()
            if not retriever:
                raise HTTPException(status_code=500, detail="Failed to initialize retriever")
            
            # Get request history for context
            context_query = get_request_history(request.user_id) if request.include_history else request.question
            logger.info(f"Using context query for retrieval: {context_query[:100]}...")
            
            # Retrieve relevant documents
            retrieved_docs = retriever.invoke(context_query)
            context = "\n".join([doc.page_content for doc in retrieved_docs])
            
            # Prepare sources
            sources = []
            for doc in retrieved_docs:
                source = None
                metadata = {}
                
                if hasattr(doc, 'metadata'):
                    source = doc.metadata.get('source', None)
                    metadata = {k: v for k, v in doc.metadata.items() if k not in ['text', 'source']}
                
                sources.append(SourceDocument(
                    text=doc.page_content,
                    source=source,
                    score=getattr(doc, 'score', None),
                    metadata=metadata
                ))
        else:
            # No RAG
            context = ""
            sources = None
        
        # Get chat history
        chat_history = get_chat_history(request.user_id) if request.include_history else ""
        logger.info(f"Using chat history: {chat_history[:100]}...")
        
        # Initialize Gemini model
        generation_config = {
            "temperature": 0.9,
            "top_p": 1,
            "top_k": 1,
            "max_output_tokens": 2048,
        }

        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
        ]

        model = genai.GenerativeModel(
            model_name='models/gemini-2.0-flash',
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Generate the prompt using template
        prompt_text = prompt.format(
            context=context,
            question=request.question,
            chat_history=chat_history
        )
        logger.info(f"Full prompt with history and context: {prompt_text[:200]}...")
        
        # Generate response
        response = model.generate_content(prompt_text)
        answer = response.text
        
        # Save the RAG response
        try:
            # Now save the RAG response with the same session_id
            save_session(
                session_id=session_id,
                factor="rag",
                action="RAG_response",
                first_name=getattr(request, 'first_name', "User"),
                last_name=getattr(request, 'last_name', ""),
                message=request.question,
                user_id=request.user_id,
                username=getattr(request, 'username', ""),
                response=answer
            )
            logger.info(f"RAG response saved for session {session_id}")
            
            # Check if the response starts with "I don't know" and trigger notification
            if answer.strip().lower().startswith("i don't know"):
                from app.api.websocket_routes import send_notification
                notification_data = {
                    "session_id": session_id,
                    "factor": "rag",
                    "action": "RAG_response",
                    "message": request.question,
                    "user_id": request.user_id,
                    "username": getattr(request, 'username', ""),
                    "first_name": getattr(request, 'first_name', "User"),
                    "last_name": getattr(request, 'last_name', ""),
                    "response": answer,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                background_tasks.add_task(send_notification, notification_data)
                logger.info(f"Notification queued for session {session_id} - response starts with 'I don't know'")
        except Exception as e:
            logger.error(f"Error saving RAG response to session: {e}")
            # Continue processing even if saving fails
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Create internal response object with sources for logging
        internal_response = ChatResponseInternal(
            answer=answer,
            sources=sources,
            processing_time=processing_time
        )
        
        # Log full response with sources
        logger.info(f"Generated response for user {request.user_id}: {answer}")
        if sources:
            logger.info(f"Sources used: {len(sources)} documents")
            for i, source in enumerate(sources):
                logger.info(f"Source {i+1}: {source.source or 'Unknown'} (score: {source.score})")
        
        # Create response object for API (without sources)
        chat_response = ChatResponse(
            answer=answer,
            processing_time=processing_time
        )
        
        # Cache result using redis_client instead of cache
        try:
            # Convert to JSON to ensure it can be cached
            cache_data = {
                "answer": answer,
                "processing_time": processing_time
            }
            await redis_client.set(cache_key, json.dumps(cache_data), ex=300)
        except Exception as e:
            logger.error(f"Error caching response: {e}")
            # Continue even if caching fails
        
        # Return response
        return chat_response
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to process chat request: {str(e)}")

# Health check endpoint
@router.get("/health")
async def health_check():
    """
    Check health of RAG services.
    """
    services = {
        "gemini": False,
        "pinecone": False
    }
    
    # Check Gemini
    try:
        # Initialize simple model
        model = genai.GenerativeModel("gemini-2.0-flash")
        # Test generation
        response = model.generate_content("Hello")
        services["gemini"] = True
    except Exception as e:
        logger.error(f"Gemini health check failed: {e}")
    
    # Check Pinecone
    try:
        # Import pinecone function
        from app.database.pinecone import get_pinecone_index
        # Get index
        index = get_pinecone_index()
        # Check if index exists
        if index:
            services["pinecone"] = True
    except Exception as e:
        logger.error(f"Pinecone health check failed: {e}")
    
    # Return health status
    status = "healthy" if all(services.values()) else "degraded"
    return {
        "status": status, 
        "services": services, 
        "timestamp": datetime.now().isoformat()
    }

@router.post("/rag")
async def process_rag(request: Request, user_data: UserMessageModel, background_tasks: BackgroundTasks):
    """Process a user message through the RAG pipeline and return a response."""
    try:
        # Extract request data
        user_id = user_data.user_id
        session_id = user_data.session_id
        message = user_data.message
        
        logger.info(f"RAG request received for user_id={user_id}, session_id={session_id}")
        logger.info(f"Message: {message[:100]}..." if len(message) > 100 else f"Message: {message}")
        
        # Create a cache key for this request to avoid reprocessing identical questions
        cache_key = f"rag_{user_id}_{session_id}_{hashlib.md5(message.encode()).hexdigest()}"
        
        # Check if we have this response cached
        cached_result = await redis_client.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for key: {cache_key}")
            if isinstance(cached_result, str):  # If stored as JSON string
                return json.loads(cached_result)
            return cached_result
        
        # Save user message to MongoDB
        try:
            # Save user's question
            save_session(
                session_id=session_id,
                factor="user",
                action="asking_freely",
                first_name="User",  # You can update this with actual data if available
                last_name="",
                message=message,
                user_id=user_id,
                username="",
                response=None  # No response yet
            )
            logger.info(f"User message saved for session {session_id}")
        except Exception as e:
            logger.error(f"Error saving user message to MongoDB: {e}")
            # Continue processing even if saving fails
        
        # Get relevant docs using retriever
        retriever = get_chain()
        if not retriever:
            raise HTTPException(status_code=500, detail="Failed to initialize retriever")
            
        # Get request history for context
        context_query = get_request_history(user_id) or message
        logger.info(f"Using context query for retrieval: {context_query[:100]}...")
        
        # Retrieve relevant documents
        retrieved_docs = retriever.invoke(context_query)
        context = "\n".join([doc.page_content for doc in retrieved_docs])
        
        # Get chat history
        chat_history = get_chat_history(user_id)
        logger.info(f"Using chat history: {chat_history[:100]}...")
        
        # Initialize Gemini model
        generation_config = {
            "temperature": 0.9,
            "top_p": 1,
            "top_k": 1,
            "max_output_tokens": 2048,
        }

        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
        ]

        model = genai.GenerativeModel(
            model_name='models/gemini-2.0-flash',
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Generate the prompt using template
        prompt_text = prompt.format(
            context=context,
            question=message,
            chat_history=chat_history
        )
        logger.info(f"Full prompt with history and context: {prompt_text[:200]}...")
        
        # Generate response
        response = model.generate_content(prompt_text)
        answer = response.text
        
        # Save the RAG response
        try:
            # Now save the RAG response with the same session_id
            save_session(
                session_id=session_id,
                factor="rag",
                action="RAG_response",
                first_name="User",
                last_name="",
                message=message,
                user_id=user_id,
                username="",
                response=answer
            )
            logger.info(f"RAG response saved for session {session_id}")
            
            # Check if the response starts with "I don't know" and trigger notification
            if answer.strip().lower().startswith("i don't know"):
                from app.api.websocket_routes import send_notification
                notification_data = {
                    "session_id": session_id,
                    "factor": "rag",
                    "action": "RAG_response",
                    "message": message,
                    "user_id": user_id,
                    "username": "",
                    "first_name": "User",
                    "last_name": "",
                    "response": answer,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                background_tasks.add_task(send_notification, notification_data)
                logger.info(f"Notification queued for session {session_id} - response starts with 'I don't know'")
        except Exception as e:
            logger.error(f"Error saving RAG response to session: {e}")
            # Continue processing even if saving fails
        
        # Prepare sources for the response
        sources = []
        for doc in retrieved_docs:
            source = None
            metadata = {}
            
            if hasattr(doc, 'metadata'):
                source = doc.metadata.get('source', None)
                metadata = {k: v for k, v in doc.metadata.items() if k not in ['text', 'source']}
            
            sources.append({
                "text": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                "source": source,
                "score": getattr(doc, 'score', None),
                "metadata": metadata
            })
        
        # Create response
        result = {
            "answer": answer,
            "sources": sources
        }
        
        # Cache the result
        result_json = json.dumps(result)
        await redis_client.set(cache_key, result_json, ex=300)
        logger.info(f"Result cached with key {cache_key}")
        
        return result
    
    except Exception as e:
        logger.error(f"Error in RAG process: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"RAG processing error: {str(e)}") 