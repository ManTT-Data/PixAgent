from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
import logging
import time
import os
import google.generativeai as genai
from datetime import datetime

from app.database.mongodb import get_user_history
from app.database.pinecone import search_vectors
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

# Helper for embeddings
async def get_embedding(text: str):
    """Get embedding from Google Gemini API"""
    try:
        # Initialize embedding model
        embedding_model = genai.GenerativeModel("embedding-001")
        
        # Generate embedding
        result = embedding_model.embed_content(text)
        
        # Return embedding
        return {
            "embedding": result.embedding,
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

# Main chat endpoint
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
        # Initialize answer model
        answer_model = genai.GenerativeModel("gemini-1.5-pro")
        
        # Get user history if requested
        history = []
        if request.include_history:
            history = get_user_history(request.user_id)
        
        # Get embedding for question
        embedding_data = await get_embedding(request.question)
        query_embedding = embedding_data["embedding"]
        
        # Initialize context with relevant information
        context = ""
        sources = []
        
        # Search Pinecone for relevant information if RAG is enabled
        if request.use_rag:
            # Search for similar vectors
            search_results = await search_vectors(
                query_vector=query_embedding,
                top_k=request.similarity_top_k,
                filter=None
            )
            
            # Extract relevant text and add to context
            if search_results and hasattr(search_results, "matches"):
                for match in search_results.matches:
                    if match.score >= request.vector_distance_threshold:
                        if "text" in match.metadata:
                            context += match.metadata["text"] + "\n\n"
                            
                            # Add to sources
                            sources.append(SourceDocument(
                                text=match.metadata["text"],
                                source=match.metadata.get("source", None),
                                score=match.score,
                                metadata={k: v for k, v in match.metadata.items() if k not in ["text", "source"]}
                            ))
        
        # Build prompt with context, history, and question
        prompt = ""
        
        # Add context if available
        if context:
            prompt += f"Context information:\n{context}\n\n"
        
        # Add history if available
        if history:
            prompt += "Previous conversation:\n"
            for qa in history:
                prompt += f"User: {qa['question']}\nAssistant: {qa['answer']}\n"
            prompt += "\n"
        
        # Add current question
        prompt += f"User: {request.question}\nAssistant: "
        
        # Generate response
        response = answer_model.generate_content(prompt)
        answer = response.text
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Return response
        return ChatResponse(
            answer=answer,
            sources=sources if sources else None,
            processing_time=processing_time
        )
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
        model = genai.GenerativeModel("gemini-1.5-flash")
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