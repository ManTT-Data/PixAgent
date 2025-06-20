from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

# --- FAQ Models ---
class FAQBase(BaseModel):
    question: str
    answer: str
    is_active: bool = True

class FAQCreate(FAQBase):
    pass

class FAQUpdate(FAQBase):
    question: Optional[str] = None
    answer: Optional[str] = None
    is_active: Optional[bool] = None

class FAQResponse(FAQBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class BatchFAQCreate(BaseModel):
    items: List[FAQCreate]

# --- Emergency Contact Models ---
class EmergencyBase(BaseModel):
    name: str
    phone_number: str
    description: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    priority: int = 0
    is_active: bool = True
    section: Optional[str] = None
    section_id: Optional[int] = None

class EmergencyCreate(EmergencyBase):
    pass

class EmergencyUpdate(EmergencyBase):
    name: Optional[str] = None
    phone_number: Optional[str] = None

class EmergencyResponse(EmergencyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class BatchEmergencyCreate(BaseModel):
    items: List[EmergencyCreate]

# --- Event Models ---
class EventBase(BaseModel):
    name: str
    description: str
    address: str
    location: Optional[str] = None
    date_start: datetime
    date_end: Optional[datetime] = None
    price: Optional[Dict[str, Any]] = None
    url: Optional[str] = None
    is_active: bool = True
    featured: bool = False

class EventCreate(EventBase):
    pass

class EventUpdate(EventBase):
    name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None

class EventResponse(EventBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class BatchEventCreate(BaseModel):
    items: List[EventCreate]

# --- Batch Update Models ---
class BatchUpdateResult(BaseModel):
    success: bool
    updated_count: int
    error_message: Optional[str] = None

# --- Info Content Models ---
class InfoContentBase(BaseModel):
    content: str

class InfoContentUpdate(InfoContentBase):
    pass

class InfoContentResponse(InfoContentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- API Key Models ---
class ApiKeyBase(BaseModel):
    key_type: str
    key_value: str
    description: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True

class ApiKeyCreate(ApiKeyBase):
    pass

class ApiKeyUpdate(ApiKeyBase):
    key_type: Optional[str] = None
    key_value: Optional[str] = None
    is_active: Optional[bool] = None

class ApiKeyResponse(ApiKeyBase):
    id: int
    created_at: datetime
    last_used: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

# --- Vector Database Models ---
class VectorDatabaseBase(BaseModel):
    name: str
    description: Optional[str] = None
    pinecone_index: str
    api_key_id: Optional[int] = None
    status: str = "active"

class VectorDatabaseCreate(VectorDatabaseBase):
    pass

class VectorDatabaseUpdate(VectorDatabaseBase):
    name: Optional[str] = None
    pinecone_index: Optional[str] = None
    status: Optional[str] = None

class VectorDatabaseResponse(VectorDatabaseBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class VectorDatabaseDetailResponse(VectorDatabaseResponse):
    document_count: int
    total_vectors: int
    namespace: str

# --- Document Models ---
class DocumentBase(BaseModel):
    name: str
    vector_database_id: int

class DocumentCreate(DocumentBase):
    pass

class DocumentUpdate(BaseModel):
    name: Optional[str] = None

class DocumentResponse(BaseModel):
    id: int
    name: str
    file_type: str
    content_type: Optional[str] = None
    size: int
    created_at: datetime
    updated_at: datetime
    vector_database_id: int
    vector_database_name: Optional[str] = None
    is_embedded: bool
    
    model_config = ConfigDict(from_attributes=True)

# --- Telegram Bot Models ---
class TelegramBotBase(BaseModel):
    name: str
    username: str
    token: str
    status: str = "inactive"

class TelegramBotUpdate(BaseModel):
    name: Optional[str] = None
    token: Optional[str] = None
    status: Optional[str] = None

class TelegramBotResponse(TelegramBotBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- Chat Engine Models ---
class ChatEngineBase(BaseModel):
    name: str
    answer_model: str
    system_prompt: Optional[str] = None
    empty_response: Optional[str] = None
    similarity_top_k: int = 3
    vector_distance_threshold: float = 0.75
    grounding_threshold: float = 0.2
    use_public_information: bool = False
    status: str = "active"

class ChatEngineCreate(ChatEngineBase):
    pass

class ChatEngineUpdate(ChatEngineBase):
    name: Optional[str] = None
    answer_model: Optional[str] = None
    status: Optional[str] = None

class ChatEngineResponse(ChatEngineBase):
    id: int
    created_at: datetime
    last_modified: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- Bot Engine Models ---
class BotEngineBase(BaseModel):
    bot_id: int
    engine_id: int

class BotEngineCreate(BotEngineBase):
    pass

class BotEngineResponse(BotEngineBase):
    id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- Engine Vector DB Models ---
class EngineVectorDbBase(BaseModel):
    engine_id: int
    vector_database_id: int
    priority: int = 0

class EngineVectorDbCreate(EngineVectorDbBase):
    pass

class EngineVectorDbResponse(EngineVectorDbBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

# --- Vector Status Models ---
class VectorStatusResponse(BaseModel):
    id: int
    document_id: int
    vector_database_id: int
    vector_id: Optional[str] = None
    document_name: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    embedded_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

# --- Merge Operation Models ---
class DatabaseMergeRequest(BaseModel):
    """
    Request model for merging vector databases.
    """
    source_database_ids: List[int] = Field(..., description="List of source database IDs to merge")
    target_name: str = Field(..., description="Name for the new merged database")
    target_index_name: str = Field(..., description="Pinecone index name for the merged database")
    target_api_key: Optional[str] = Field(None, description="Optional new API key for the merged database")
    description: Optional[str] = Field(None, description="Optional description for the merged database")

class MergeProgressResponse(BaseModel):
    """
    Response model for merge operation progress.
    """
    database_id: int = Field(..., description="ID of the target database")
    status: str = Field(..., description="Current status of the merge operation")
    total_documents: int = Field(0, description="Total number of documents to process")
    processed_documents: int = Field(0, description="Number of documents processed successfully")
    failed_documents: int = Field(0, description="Number of documents that failed to process")
    current_document: Optional[str] = Field(None, description="Name of the document currently being processed")
    error_message: Optional[str] = Field(None, description="Error message if the merge operation failed")
    created_at: datetime = Field(..., description="When the merge operation was created")
    updated_at: datetime = Field(..., description="When the merge operation was last updated")

class MergeStatusResponse(BaseModel):
    """
    Response model for merge operation status.
    """
    merge_id: str = Field(..., description="Unique identifier for the merge operation")
    source_databases: List[int] = Field(..., description="List of source database IDs")
    target_database_id: int = Field(..., description="ID of the target database")
    status: str = Field(..., description="Current status of the merge operation")
    progress: MergeProgressResponse = Field(..., description="Detailed progress information")
    created_at: datetime = Field(..., description="When the merge operation was created")
    updated_at: datetime = Field(..., description="When the merge operation was last updated")

# --- Da Nang Bucket List Models ---
class DaNangBucketListBase(BaseModel):
    content: str

class DaNangBucketListCreate(DaNangBucketListBase):
    pass

class DaNangBucketListUpdate(BaseModel):
    content: Optional[str] = None

class DaNangBucketListResponse(DaNangBucketListBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True) 