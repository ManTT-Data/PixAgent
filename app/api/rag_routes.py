from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
import logging
import time
import os
import google.generativeai as genai
from datetime import datetime
from langchain.prompts import PromptTemplate
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.utils.utils import cache, timer_decorator

from app.database.mongodb import get_user_history, get_chat_history, get_request_history, save_session
from app.database.pinecone import (
    search_vectors, 
    get_chain, 
)
from app.models.rag_models import (
    ChatRequest,
    ChatResponse,
    SourceDocument,
    EmbeddingRequest,
    EmbeddingResponse
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
    """
    start_time = time.time()
    try:
        # Tạo cache key cho request
        cache_key = f"rag_chat:{request.user_id}:{request.question}:{request.include_history}:{request.use_rag}"
        
        # Kiểm tra cache
        cached_response = cache.get(cache_key)
        if cached_response is not None:
            logger.info(f"Cache hit for RAG chat request from user {request.user_id}")
            return cached_response
        
        # Use the RAG pipeline
        if request.use_rag:
            # Get the retriever
            retriever = get_chain()
            if not retriever:
                raise HTTPException(status_code=500, detail="Failed to initialize retriever")
            
            # Get request history for context
            context_query = get_request_history(request.user_id) if request.include_history else request.question
            
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
        logger.info(f"Prompt: {prompt_text}")
        # Generate response
        response = model.generate_content(prompt_text)
        answer = response.text
        
        # Lưu phản hồi vào session nếu có thông tin về user
        if request.user_id and hasattr(request, 'session_id') and request.session_id:
            try:
                # Dùng chung session_id nếu đã được cung cấp từ request
                session_id = request.session_id
                
                # Thêm session mới cho phản hồi RAG
                background_tasks.add_task(
                    save_session,
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
            except Exception as e:
                logger.error(f"Error saving RAG response to session: {e}")
                # Không dừng xử lý chính nếu lưu session thất bại
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Tạo response object
        chat_response = ChatResponse(
            answer=answer,
            sources=sources,
            processing_time=processing_time
        )
        
        # Cache kết quả trong 5 phút
        cache.set(cache_key, chat_response, ttl=300)
        
        # Return response
        return chat_response
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
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