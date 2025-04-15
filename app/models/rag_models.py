from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    user_id: str
    question: str
    include_history: bool = True
    use_rag: bool = True
    similarity_top_k: Optional[int] = 3
    vector_distance_threshold: Optional[float] = 0.75

class SourceDocument(BaseModel):
    """Model for source documents"""
    text: str
    source: Optional[str] = None
    score: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    answer: str
    sources: Optional[List[SourceDocument]] = None
    processing_time: Optional[float] = None

class EmbeddingRequest(BaseModel):
    """Request model for embedding endpoint"""
    text: str

class EmbeddingResponse(BaseModel):
    """Response model for embedding endpoint"""
    embedding: List[float]
    text: str
    model: str

class HealthResponse(BaseModel):
    """Response model for health endpoint"""
    status: str
    services: Dict[str, bool]
    timestamp: str 