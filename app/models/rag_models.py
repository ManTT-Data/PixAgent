from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    user_id: str = Field(..., description="User ID from Telegram")
    question: str = Field(..., description="User's question")
    include_history: bool = Field(True, description="Whether to include user history in prompt")
    use_rag: bool = Field(True, description="Whether to use RAG")
    
    # Advanced retrieval parameters
    similarity_top_k: int = Field(6, description="Number of top similar documents to return (after filtering)")
    limit_k: int = Field(10, description="Maximum number of documents to retrieve from vector store")
    similarity_metric: str = Field("cosine", description="Similarity metric to use (cosine, dotproduct, euclidean)")
    similarity_threshold: float = Field(0.75, description="Threshold for vector similarity (0-1)")
    
    # User information
    session_id: Optional[str] = Field(None, description="Session ID for tracking conversations")
    first_name: Optional[str] = Field(None, description="User's first name")
    last_name: Optional[str] = Field(None, description="User's last name")
    username: Optional[str] = Field(None, description="User's username")

class SourceDocument(BaseModel):
    """Model for source documents"""
    text: str = Field(..., description="Text content of the document")
    source: Optional[str] = Field(None, description="Source of the document")
    score: Optional[float] = Field(None, description="Raw similarity score of the document")
    normalized_score: Optional[float] = Field(None, description="Normalized similarity score (0-1)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata of the document")

class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    answer: str = Field(..., description="Generated answer")
    processing_time: float = Field(..., description="Processing time in seconds")

class ChatResponseInternal(BaseModel):
    """Internal model for chat response with sources - used only for logging"""
    answer: str
    sources: Optional[List[SourceDocument]] = Field(None, description="Source documents used for generating answer")
    processing_time: Optional[float] = None

class EmbeddingRequest(BaseModel):
    """Request model for embedding endpoint"""
    text: str = Field(..., description="Text to generate embedding for")

class EmbeddingResponse(BaseModel):
    """Response model for embedding endpoint"""
    embedding: List[float] = Field(..., description="Generated embedding")
    text: str = Field(..., description="Text that was embedded")
    model: str = Field(..., description="Model used for embedding")

class HealthResponse(BaseModel):
    """Response model for health endpoint"""
    status: str
    services: Dict[str, bool]
    timestamp: str

class UserMessageModel(BaseModel):
    """Model for user messages sent to the RAG API"""
    user_id: str = Field(..., description="User ID from the client application")
    session_id: str = Field(..., description="Session ID for tracking the conversation")
    message: str = Field(..., description="User's message/question")
    
    # Advanced retrieval parameters (optional)
    similarity_top_k: Optional[int] = Field(None, description="Number of top similar documents to return (after filtering)")
    limit_k: Optional[int] = Field(None, description="Maximum number of documents to retrieve from vector store")
    similarity_metric: Optional[str] = Field(None, description="Similarity metric to use (cosine, dotproduct, euclidean)")
    similarity_threshold: Optional[float] = Field(None, description="Threshold for vector similarity (0-1)") 