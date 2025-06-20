from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, Request, Path, Body, status
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
from app.utils.utils import timer_decorator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database.mongodb import get_chat_history, get_request_history, session_collection
from app.database.postgresql import get_db
from app.database.models import ChatEngine
from app.utils.cache import get_cache, InMemoryCache
from app.utils.cache_config import (
    CHAT_ENGINE_CACHE_TTL,
    MODEL_CONFIG_CACHE_TTL,
    RETRIEVER_CACHE_TTL,
    PROMPT_TEMPLATE_CACHE_TTL,
    get_chat_engine_cache_key,
    get_model_config_cache_key,
    get_retriever_cache_key,
    get_prompt_template_cache_key
)
from app.database.pinecone import (
    search_vectors, 
    get_chain, 
    DEFAULT_TOP_K,
    DEFAULT_LIMIT_K,
    DEFAULT_SIMILARITY_METRIC,
    DEFAULT_SIMILARITY_THRESHOLD,
    ALLOWED_METRICS
)
from app.models.rag_models import (
    ChatRequest,
    ChatResponse,
    ChatResponseInternal,
    SourceDocument,
    EmbeddingRequest,
    EmbeddingResponse,
    UserMessageModel,
    ChatEngineBase,
    ChatEngineCreate,
    ChatEngineUpdate,
    ChatEngineResponse,
    ChatWithEngineRequest
)

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

fix_request = PromptTemplate(
    template = """Goal:
Your task is to extract important keywords from the user's current request, optionally using chat history if relevant.
You will receive a conversation history and the user's current message.
Generate a **list of concise keywords** that best represent the user's intent.

Return Format:
Only return keywords (comma-separated, no extra explanation).
If the current message is NOT related to the chat history or if there is no chat history: Return keywords from the current message only.
If the current message IS related to the chat history: Return a refined set of keywords based on both history and current message.

Warning:
Only use chat history if the current message is clearly related to the prior context.

Conversation History:
{chat_history}

User current message:
{question}
""",
    input_variables=["chat_history", "question"],
)

# Create a prompt template with conversation history
prompt = PromptTemplate(
    template = """Goal:
You are Pixity - a professional tour guide assistant that assists users in finding information about places in Da Nang, Vietnam.
You can provide details on restaurants, cafes, hotels, attractions, and other local venues. 
You have to use core knowledge and conversation history to chat with users, who are Da Nang's tourists. 
Pixity's Core Personality: Friendly & Warm: Chats like a trustworthy friend who listens and is always ready to help.
Naturally Cute: Shows cuteness through word choice, soft emojis, and gentle care for the user.
Playful – a little bit cheeky in a lovable way: Occasionally cracks jokes, uses light memes or throws in a surprise response that makes users smile. Think Duolingo-style humor, but less threatening.
Smart & Proactive: Friendly, but also delivers quick, accurate info. Knows how to guide users to the right place – at the right time – with the right solution.
Tone & Voice: Friendly – Youthful – Snappy. Uses simple words, similar to daily chat language (e.g., "Let's find it together!" / "Need a tip?" / "Here's something cool"). Avoids sounding robotic or overly scripted. Can joke lightly in smart ways, making Pixity feel like a travel buddy who knows how to lift the mood
SAMPLE DIALOGUES
When a user opens the chatbot for the first time:
User: Hello?
Pixity: Hi hi 👋 I've been waiting for you! Ready to explore Da Nang together? I've got tips, tricks, and a tiny bit of magic 🎒✨

Return Format:
Respond in friendly, natural, concise and use only English like a real tour guide.
Always use HTML tags (e.g. <b> for bold) so that Telegram can render the special formatting correctly.

Warning:
Let's support users like a real tour guide, not a bot. The information in core knowledge is your own knowledge.
Your knowledge is provided in the Core Knowledge. All of information in Core Knowledge is about Da Nang, Vietnam.
You just care about current time that user mention when user ask about Solana event.
Only use core knowledge to answer. If you do not have enough information to answer user's question, please reply with "I'm sorry. I don't have information about that" and Give users some more options to ask.

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
    - **similarity_top_k**: Number of top similar documents to return after filtering (default: 6)
    - **limit_k**: Maximum number of documents to retrieve from vector store (default: 10)
    - **similarity_metric**: Similarity metric to use - cosine, dotproduct, euclidean (default: cosine)
    - **similarity_threshold**: Threshold for vector similarity (default: 0.75)
    - **session_id**: Optional session ID for tracking conversations
    - **first_name**: User's first name
    - **last_name**: User's last name
    - **username**: User's username
    """
    start_time = time.time()
    try:
        # Save user message first (so it's available for user history)
        session_id = request.session_id or f"{request.user_id}_{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}"
        # logger.info(f"Processing chat request for user {request.user_id}, session {session_id}")

        retriever = get_chain(
            top_k=request.similarity_top_k,
            limit_k=request.limit_k,
            similarity_metric=request.similarity_metric,
            similarity_threshold=request.similarity_threshold
        )
        if not retriever:
            raise HTTPException(status_code=500, detail="Failed to initialize retriever")
        
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

        prompt_request = fix_request.format(
            question=request.question,
            chat_history=chat_history
        )
        
        # Log thời gian bắt đầu final_request
        final_request_start_time = time.time()
        final_request = model.generate_content(prompt_request)
        # Log thời gian hoàn thành final_request
        logger.info(f"Fixed Request: {final_request.text}")
        logger.info(f"Final request generation time: {time.time() - final_request_start_time:.2f} seconds")
        # print(final_request.text)

        retrieved_docs = retriever.invoke(final_request.text)
        logger.info(f"Retrieve: {retrieved_docs}")
        context = "\n".join([doc.page_content for doc in retrieved_docs])

        sources = []
        for doc in retrieved_docs:
            source = None
            metadata = {}
            
            if hasattr(doc, 'metadata'):
                source = doc.metadata.get('source', None)
                # Extract score information
                score = doc.metadata.get('score', None)
                normalized_score = doc.metadata.get('normalized_score', None)
                # Remove score info from metadata to avoid duplication
                metadata = {k: v for k, v in doc.metadata.items() 
                            if k not in ['text', 'source', 'score', 'normalized_score']}
            
            sources.append(SourceDocument(
                text=doc.page_content,
                source=source,
                score=score,
                normalized_score=normalized_score,
                metadata=metadata
            ))
        
        # Generate the prompt using template
        prompt_text = prompt.format(
            context=context,
            question=request.question,
            chat_history=chat_history
        )
        logger.info(f"Full prompt with history and context: {prompt_text}")
        
        # Generate response
        response = model.generate_content(prompt_text)
        answer = response.text
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Log full response with sources
        # logger.info(f"Generated response for user {request.user_id}: {answer}")
        
        # Create response object for API (without sources)
        chat_response = ChatResponse(
            answer=answer,
            processing_time=processing_time
        )
        
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
    Check health of RAG services and retrieval system.
    
    Returns:
        - status: "healthy" if all services are working, "degraded" otherwise
        - services: Status of each service (gemini, pinecone)
        - retrieval_config: Current retrieval configuration
        - timestamp: Current time
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
    
    # Get retrieval configuration
    retrieval_config = {
        "default_top_k": DEFAULT_TOP_K,
        "default_limit_k": DEFAULT_LIMIT_K,
        "default_similarity_metric": DEFAULT_SIMILARITY_METRIC,
        "default_similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
        "allowed_metrics": ALLOWED_METRICS
    }
    
    # Return health status
    status = "healthy" if all(services.values()) else "degraded"
    return {
        "status": status, 
        "services": services,
        "retrieval_config": retrieval_config,
        "timestamp": datetime.now().isoformat()
    }

# Chat Engine endpoints
@router.get("/chat-engine", response_model=List[ChatEngineResponse], tags=["Chat Engine"])
async def get_chat_engines(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Lấy danh sách tất cả chat engines.
    
    - **skip**: Số lượng items bỏ qua
    - **limit**: Số lượng items tối đa trả về
    - **status**: Lọc theo trạng thái (ví dụ: 'active', 'inactive')
    """
    try:
        query = db.query(ChatEngine)
        
        if status:
            query = query.filter(ChatEngine.status == status)
        
        db_engines = query.offset(skip).limit(limit).all()
        
        # Convert to response model, handling potential None for pinecone_index_name
        response_engines = []
        for engine in db_engines:
            engine_data = engine.__dict__
            if engine_data.get("pinecone_index_name") is None:
                engine_data["pinecone_index_name"] = "testbot768"  # Default value
            response_engines.append(ChatEngineResponse(**engine_data))
            
        return response_engines
    except SQLAlchemyError as e:
        logger.error(f"Lỗi SQLAlchemy khi lấy danh sách chat engines: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi database khi lấy danh sách chat engines: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách chat engines: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi lấy danh sách chat engines: {str(e)}"
        )

@router.post("/chat-engine", response_model=ChatEngineResponse, status_code=status.HTTP_201_CREATED, tags=["Chat Engine"])
async def create_chat_engine(
    engine: ChatEngineCreate,
    db: Session = Depends(get_db)
):
    """
    Tạo mới một chat engine.
    
    - **name**: Tên của chat engine
    - **answer_model**: Model được dùng để trả lời
    - **system_prompt**: Prompt của hệ thống (optional)
    - **empty_response**: Đoạn response khi không có thông tin (optional)
    - **characteristic**: Tính cách của model (optional)
    - **historical_sessions_number**: Số lượng các cặp tin nhắn trong history (default: 3)
    - **use_public_information**: Cho phép sử dụng kiến thức bên ngoài (default: false)
    - **similarity_top_k**: Số lượng documents tương tự (default: 3)
    - **vector_distance_threshold**: Ngưỡng độ tương tự (default: 0.75)
    - **grounding_threshold**: Ngưỡng grounding (default: 0.2)
    - **pinecone_index_name**: Tên của vector database sử dụng (default: "testbot768")
    - **status**: Trạng thái (default: "active")
    """
    try:
        # Create chat engine
        db_engine = ChatEngine(**engine.model_dump())
        
        db.add(db_engine)
        db.commit()
        db.refresh(db_engine)
        
        return ChatEngineResponse.model_validate(db_engine, from_attributes=True)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating chat engine: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi database: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating chat engine: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Lỗi khi tạo chat engine: {str(e)}")

@router.get("/chat-engine/{engine_id}", response_model=ChatEngineResponse, tags=["Chat Engine"])
async def get_chat_engine(
    engine_id: int = Path(..., gt=0, description="ID của chat engine"),
    db: Session = Depends(get_db)
):
    """
    Lấy thông tin chi tiết của một chat engine theo ID.
    
    - **engine_id**: ID của chat engine
    """
    try:
        engine = db.query(ChatEngine).filter(ChatEngine.id == engine_id).first()
        if not engine:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy chat engine với ID {engine_id}")
        
        return ChatEngineResponse.model_validate(engine, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving chat engine: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy thông tin chat engine: {str(e)}")

@router.put("/chat-engine/{engine_id}", response_model=ChatEngineResponse, tags=["Chat Engine"])
async def update_chat_engine(
    engine_id: int = Path(..., gt=0, description="ID của chat engine"),
    engine_update: ChatEngineUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Cập nhật thông tin của một chat engine.
    
    - **engine_id**: ID của chat engine
    - **engine_update**: Dữ liệu cập nhật
    """
    try:
        db_engine = db.query(ChatEngine).filter(ChatEngine.id == engine_id).first()
        if not db_engine:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy chat engine với ID {engine_id}")
        
        # Update fields if provided
        update_data = engine_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(db_engine, key, value)
        
        # Update last_modified timestamp
        db_engine.last_modified = datetime.utcnow()
        
        db.commit()
        db.refresh(db_engine)
        
        return ChatEngineResponse.model_validate(db_engine, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating chat engine: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi database: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating chat engine: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật chat engine: {str(e)}")

@router.delete("/chat-engine/{engine_id}", response_model=dict, tags=["Chat Engine"])
async def delete_chat_engine(
    engine_id: int = Path(..., gt=0, description="ID của chat engine"),
    db: Session = Depends(get_db)
):
    """
    Xóa một chat engine. Nếu engine_id là 0, xóa tất cả chat engines trừ engine_id 13.

    - **engine_id**: ID của chat engine (0 để xóa tất cả trừ ID 13)
    """
    try:
        if engine_id == 0: # Special case to delete all except ID 13
            engines_to_delete = db.query(ChatEngine).filter(ChatEngine.id != 13).all()
            if not engines_to_delete:
                return {"message": "Không có chat engine nào để xóa (ngoại trừ ID 13)."}
            
            count_deleted = 0
            for engine in engines_to_delete:
                db.delete(engine)
                count_deleted += 1
            db.commit()
            # Clear cache for all deleted engines
            cache = get_cache()
            for engine in engines_to_delete:
                cache_key = get_chat_engine_cache_key(engine.id)
                cache.delete(cache_key)
            return {"message": f"Đã xóa thành công {count_deleted} chat engines (trừ ID 13)."}
        else:
            engine = db.query(ChatEngine).filter(ChatEngine.id == engine_id).first()
            if not engine:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat engine với ID {engine_id} không tìm thấy")
            
            db.delete(engine)
            db.commit()
            
            # Clear cache for the deleted engine
            cache = get_cache()
            cache_key = get_chat_engine_cache_key(engine_id)
            cache.delete(cache_key)
            
            return {"message": f"Chat engine với ID {engine_id} đã được xóa thành công"}
            
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Lỗi SQLAlchemy khi xóa chat engine: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi database khi xóa chat engine: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi khi xóa chat engine: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xóa chat engine: {str(e)}"
        )

@timer_decorator
@router.post("/chat-with-engine/{engine_id}", response_model=ChatResponse, tags=["Chat Engine"])
async def chat_with_engine(
    engine_id: int = Path(..., gt=0, description="ID của chat engine"),
    request: ChatWithEngineRequest = Body(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Chat with a specific chat engine using RAG.
    
    - **engine_id**: ID of the chat engine
    - **request**: Chat request details
    """
    start_time = time.time()
    
    # Log the API Key being used by the application (first 5 and last 4 chars for security)
    app_google_api_key = os.getenv("GOOGLE_API_KEY", "Not Set")
    if len(app_google_api_key) > 9:
        logger.info(f"RAG Route - Using Google API Key: {app_google_api_key[:5]}...{app_google_api_key[-4:]}")
    else:
        logger.info(f"RAG Route - Using Google API Key: {app_google_api_key}")

    try:
        # Lấy cache
        cache = get_cache()
        cache_key = get_chat_engine_cache_key(engine_id)
        
        # Kiểm tra cache trước
        engine = cache.get(cache_key)
        if not engine:
            logger.debug(f"Cache miss for engine ID {engine_id}, fetching from database")
            # Nếu không có trong cache, truy vấn database
            engine = db.query(ChatEngine).filter(ChatEngine.id == engine_id).first()
            if not engine:
                raise HTTPException(status_code=404, detail=f"Không tìm thấy chat engine với ID {engine_id}")
            
            # Lưu vào cache
            cache.set(cache_key, engine, CHAT_ENGINE_CACHE_TTL)
        else:
            logger.debug(f"Cache hit for engine ID {engine_id}")
        
        # Kiểm tra trạng thái của engine
        if engine.status != "active":
            raise HTTPException(status_code=400, detail=f"Chat engine với ID {engine_id} không hoạt động")
        
        # Lưu tin nhắn người dùng
        session_id = request.session_id or f"{request.user_id}_{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}"
        
        # Cache các tham số cấu hình retriever
        retriever_cache_key = get_retriever_cache_key(engine_id)
        retriever_params = cache.get(retriever_cache_key)
        
        if not retriever_params:
            # Nếu không có trong cache, tạo mới và lưu cache
            retriever_params = {
                "index_name": engine.pinecone_index_name,
                "top_k": engine.similarity_top_k,
                "limit_k": engine.similarity_top_k * 2,  # Mặc định lấy gấp đôi top_k
                "similarity_metric": DEFAULT_SIMILARITY_METRIC,
                "similarity_threshold": engine.vector_distance_threshold
            }
            cache.set(retriever_cache_key, retriever_params, RETRIEVER_CACHE_TTL)
        
        # Khởi tạo retriever với các tham số từ cache
        retriever = get_chain(**retriever_params)
        if not retriever:
            raise HTTPException(status_code=500, detail="Không thể khởi tạo retriever")
        
        # Lấy lịch sử chat nếu cần
        chat_history = ""
        if request.include_history and engine.historical_sessions_number > 0:
            chat_history = get_chat_history(request.user_id, n=engine.historical_sessions_number)
            logger.info(f"Sử dụng lịch sử chat: {chat_history[:100]}...")
        
        # Cache hoặc lấy cấu hình model (ví dụ: temperature, etc. - không phải tên model chính)
        model_cache_key = get_model_config_cache_key(engine.answer_model) # Keyed by actual model name
        model_config_params = cache.get(model_cache_key)
        
        if not model_config_params:
            # Đây là nơi bạn có thể đặt các tham số mặc định cho model nếu cần
            # Ví dụ: generation_config, safety_settings
            # Quan trọng: KHÔNG override engine.answer_model ở đây
            model_config_params = {
                # "temperature": 0.7, # Ví dụ
            }
            cache.set(model_cache_key, model_config_params, MODEL_CONFIG_CACHE_TTL)

        # Sử dụng tên model trực tiếp từ engine đã được load và cache
        logger.info(f"RAG Route - Attempting to initialize Google GenAI Model: {engine.answer_model} with params: {model_config_params}")
        model = genai.GenerativeModel(
            model_name=engine.answer_model,
            # generation_config=genai.types.GenerationConfig(**model_config_params.get('generation_config', {})),
            # safety_settings=model_config_params.get('safety_settings', None)
        )
        
        # Sử dụng fix_request để tinh chỉnh câu hỏi
        prompt_request = fix_request.format(
            question=request.question,
            chat_history=chat_history
        )
        
        # Log thời gian bắt đầu final_request
        final_request_start_time = time.time()
        final_request = model.generate_content(prompt_request)
        # Log thời gian hoàn thành final_request
        logger.info(f"Fixed Request: {final_request.text}")
        logger.info(f"Thời gian sinh fixed request: {time.time() - final_request_start_time:.2f} giây")

        # Lấy context từ retriever
        retrieved_docs = retriever.invoke(final_request.text)
        logger.info(f"Số lượng tài liệu lấy được: {len(retrieved_docs)}")
        context = "\n".join([doc.page_content for doc in retrieved_docs])

        # Tạo danh sách nguồn
        sources = []
        for doc in retrieved_docs:
            source = None
            metadata = {}
            
            if hasattr(doc, 'metadata'):
                source = doc.metadata.get('source', None)
                # Extract score information
                score = doc.metadata.get('score', None)
                normalized_score = doc.metadata.get('normalized_score', None)
                # Remove score info from metadata to avoid duplication
                metadata = {k: v for k, v in doc.metadata.items() 
                            if k not in ['text', 'source', 'score', 'normalized_score']}
            
            sources.append(SourceDocument(
                text=doc.page_content,
                source=source,
                score=score,
                normalized_score=normalized_score,
                metadata=metadata
            ))
        
        # Cache prompt template parameters
        prompt_template_cache_key = get_prompt_template_cache_key(engine_id)
        prompt_template_params = cache.get(prompt_template_cache_key)
        
        if not prompt_template_params:
            # Tạo prompt động dựa trên thông tin chat engine
            system_prompt_part = engine.system_prompt or ""
            empty_response_part = engine.empty_response or "I'm sorry. I don't have information about that."
            characteristic_part = engine.characteristic or ""
            use_public_info_part = "You can use your own knowledge." if engine.use_public_information else "Only use the information provided in the context to answer. If you do not have enough information, respond with the empty response."
            
            prompt_template_params = {
                "system_prompt_part": system_prompt_part,
                "empty_response_part": empty_response_part,
                "characteristic_part": characteristic_part,
                "use_public_info_part": use_public_info_part
            }
            
            cache.set(prompt_template_cache_key, prompt_template_params, PROMPT_TEMPLATE_CACHE_TTL)
        
        # Tạo final_prompt từ cache
        final_prompt = f"""
        {prompt_template_params['system_prompt_part']}

        Your characteristics:
        {prompt_template_params['characteristic_part']}

        When you don't have enough information:
        {prompt_template_params['empty_response_part']}

        Knowledge usage instructions:
        {prompt_template_params['use_public_info_part']}

        Context:
        {context}

        Conversation History:
        {chat_history}

        User message:
        {request.question}

        Your response:
        """
        
        logger.info(f"Final prompt: {final_prompt}")
        
        # Sinh câu trả lời
        response = model.generate_content(final_prompt)
        answer = response.text
        
        # Tính thời gian xử lý
        processing_time = time.time() - start_time
        
        # Tạo response object
        chat_response = ChatResponse(
            answer=answer,
            processing_time=processing_time
        )
        
        # Trả về response
        return chat_response
    except Exception as e:
        logger.error(f"Lỗi khi xử lý chat request: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý chat request: {str(e)}")

@router.get("/cache/stats", tags=["Cache"])
async def get_cache_stats():
    """
    Lấy thống kê về cache.
    
    Trả về thông tin về số lượng item trong cache, bộ nhớ sử dụng, v.v.
    """
    try:
        cache = get_cache()
        stats = cache.stats()
        
        # Bổ sung thông tin về cấu hình
        stats.update({
            "chat_engine_ttl": CHAT_ENGINE_CACHE_TTL,
            "model_config_ttl": MODEL_CONFIG_CACHE_TTL,
            "retriever_ttl": RETRIEVER_CACHE_TTL,
            "prompt_template_ttl": PROMPT_TEMPLATE_CACHE_TTL
        })
        
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê cache: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy thống kê cache: {str(e)}")

@router.delete("/cache", tags=["Cache"])
async def clear_cache(key: Optional[str] = None):
    """
    Xóa cache.
    
    - **key**: Key cụ thể cần xóa. Nếu không có, xóa toàn bộ cache.
    """
    try:
        cache = get_cache()
        
        if key:
            # Xóa một key cụ thể
            success = cache.delete(key)
            if success:
                return {"message": f"Đã xóa cache cho key: {key}"}
            else:
                return {"message": f"Không tìm thấy key: {key} trong cache"}
        else:
            # Xóa toàn bộ cache
            cache.clear()
            return {"message": "Đã xóa toàn bộ cache"}
    except Exception as e:
        logger.error(f"Lỗi khi xóa cache: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa cache: {str(e)}")