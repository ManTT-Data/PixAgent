from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import ConfigDict

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
    similarity_threshold: float = Field(0.0, description="Threshold for vector similarity (0-1)")
    
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

class ChatEngineBase(BaseModel):
    """Base model cho chat engine"""
    name: str = Field(..., description="Tên của chat engine")
    answer_model: str = Field(..., description="Model được dùng để trả lời")
    system_prompt: Optional[str] = Field(None, description="Prompt của hệ thống, được đưa vào phần đầu tiên của final_prompt")
    empty_response: Optional[str] = Field(None, description="Đoạn response khi answer model không có thông tin về câu hỏi")
    characteristic: Optional[str] = Field(None, description="Tính cách của model khi trả lời câu hỏi")
    historical_sessions_number: int = Field(3, description="Số lượng các cặp tin nhắn trong history được đưa vào final prompt")
    use_public_information: bool = Field(False, description="Yes nếu answer model được quyền trả về thông tin mà nó có")
    similarity_top_k: int = Field(3, description="Số lượng top similar documents để trả về")
    vector_distance_threshold: float = Field(0.75, description="Threshold cho vector similarity")
    grounding_threshold: float = Field(0.2, description="Threshold cho grounding")
    pinecone_index_name: str = Field("testbot768", description="Vector database mà model được quyền sử dụng")
    status: str = Field("active", description="Trạng thái của chat engine")

class ChatEngineCreate(ChatEngineBase):
    """Model cho việc tạo chat engine mới"""
    pass

class ChatEngineUpdate(BaseModel):
    """Model cho việc cập nhật chat engine"""
    name: Optional[str] = None
    answer_model: Optional[str] = None
    system_prompt: Optional[str] = None
    empty_response: Optional[str] = None
    characteristic: Optional[str] = None
    historical_sessions_number: Optional[int] = None
    use_public_information: Optional[bool] = None
    similarity_top_k: Optional[int] = None
    vector_distance_threshold: Optional[float] = None
    grounding_threshold: Optional[float] = None
    pinecone_index_name: Optional[str] = None
    status: Optional[str] = None

class ChatEngineResponse(ChatEngineBase):
    """Response model cho chat engine"""
    id: int
    created_at: datetime
    last_modified: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ChatWithEngineRequest(BaseModel):
    """Request model cho endpoint chat-with-engine"""
    user_id: str = Field(..., description="User ID from Telegram")
    question: str = Field(..., description="User's question")
    include_history: bool = Field(True, description="Whether to include user history in prompt")
    
    # User information
    session_id: Optional[str] = Field(None, description="Session ID for tracking conversations")
    first_name: Optional[str] = Field(None, description="User's first name")
    last_name: Optional[str] = Field(None, description="User's last name")
    username: Optional[str] = Field(None, description="User's username") 