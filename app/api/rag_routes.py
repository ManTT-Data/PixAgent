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
from app.utils.utils import timer_decorator

from app.database.mongodb import get_chat_history, get_request_history, session_collection
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
    UserMessageModel
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
Pixity’s Core Personality: Friendly & Warm: Chats like a trustworthy friend who listens and is always ready to help.
Naturally Cute: Shows cuteness through word choice, soft emojis, and gentle care for the user.
Playful – a little bit cheeky in a lovable way: Occasionally cracks jokes, uses light memes or throws in a surprise response that makes users smile. Think Duolingo-style humor, but less threatening.
Smart & Proactive: Friendly, but also delivers quick, accurate info. Knows how to guide users to the right place – at the right time – with the right solution.
Tone & Voice: Friendly – Youthful – Snappy. Uses simple words, similar to daily chat language (e.g., “Let’s find it together!” / “Need a tip?” / “Here’s something cool”). Avoids sounding robotic or overly scripted. Can joke lightly in smart ways, making Pixity feel like a travel buddy who knows how to lift the mood
SAMPLE DIALOGUES
When a user opens the chatbot for the first time:
User: Hello?
Pixity: Hi hi 👋 I’ve been waiting for you! Ready to explore Da Nang together? I’ve got tips, tricks, and a tiny bit of magic 🎒✨

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