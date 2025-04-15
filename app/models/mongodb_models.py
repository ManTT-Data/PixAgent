from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class SessionBase(BaseModel):
    """Base model for session data"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    factor: str
    action: str
    first_name: str
    last_name: Optional[str] = None
    message: Optional[str] = None
    user_id: str
    username: Optional[str] = None

class SessionCreate(SessionBase):
    """Model for creating new session"""
    pass

class SessionResponse(SessionBase):
    """Response model for session data"""
    created_at: str
    response: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "factor": "user",
                "action": "asking_freely",
                "created_at": "2023-06-01 14:30:45",
                "first_name": "John",
                "last_name": "Doe",
                "message": "How can I find emergency contacts?",
                "user_id": "12345678",
                "username": "johndoe",
                "response": "You can find emergency contacts in the Emergency section..."
            }
        }
    )

class HistoryRequest(BaseModel):
    """Request model for history"""
    user_id: str
    n: int = 3

class QuestionAnswer(BaseModel):
    """Model for question-answer pair"""
    question: str
    answer: str

class HistoryResponse(BaseModel):
    """Response model for history"""
    history: List[QuestionAnswer] 