from fastapi import APIRouter, HTTPException, Depends, Query, status, Response
from typing import List, Optional, Dict
from pymongo.errors import PyMongoError
import logging
from datetime import datetime
import traceback
import asyncio

from app.database.mongodb import (
    save_session, 
    get_user_history,
    update_session_response,
    check_db_connection,
    session_collection
)
from app.models.mongodb_models import (
    SessionCreate,
    SessionResponse,
    HistoryRequest,
    HistoryResponse,
    QuestionAnswer
)
from app.api.websocket_routes import send_notification

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/mongodb",
    tags=["MongoDB"],
)

@router.post("/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(session: SessionCreate, response: Response):
    """
    Create a new session record in MongoDB.
    
    - **session_id**: Unique identifier for the session (auto-generated if not provided)
    - **factor**: Factor type (user, rag, etc.)
    - **action**: Action type (start, events, faq, emergency, help, asking_freely, etc.)
    - **first_name**: User's first name
    - **last_name**: User's last name (optional)
    - **message**: User's message (optional)
    - **user_id**: User's ID from Telegram
    - **username**: User's username (optional)
    - **response**: Response from RAG (optional)
    """
    try:
        # Kiểm tra kết nối MongoDB
        if not check_db_connection():
            logger.error("MongoDB connection failed when trying to create session")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MongoDB connection failed"
            )
        
        # Create new session in MongoDB
        result = save_session(
            session_id=session.session_id,
            factor=session.factor,
            action=session.action,
            first_name=session.first_name,
            last_name=session.last_name,
            message=session.message,
            user_id=session.user_id,
            username=session.username,
            response=session.response
        )
        
        # Chuẩn bị response object
        session_response = SessionResponse(
            **session.model_dump(),
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        # Kiểm tra nếu session cần gửi thông báo (response bắt đầu bằng "I don't know")
        if session.response and session.response.strip().lower().startswith("i don't know"):
            # Gửi thông báo qua WebSocket
            try:
                notification_data = {
                    "session_id": session.session_id,
                    "factor": session.factor,
                    "action": session.action,
                    "message": session.message,
                    "user_id": session.user_id,
                    "username": session.username,
                    "first_name": session.first_name,
                    "last_name": session.last_name,
                    "response": session.response,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # Khởi tạo task để gửi thông báo - sử dụng asyncio.create_task để đảm bảo không block quá trình chính
                asyncio.create_task(send_notification(notification_data))
                logger.info(f"Notification queued for session {session.session_id} - response starts with 'I don't know'")
            except Exception as e:
                logger.error(f"Error queueing notification: {e}")
                # Không dừng xử lý chính khi gửi thông báo thất bại
        
        # Return response
        return session_response
    except PyMongoError as e:
        logger.error(f"MongoDB error creating session: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MongoDB error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error creating session: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )

@router.put("/session/{session_id}/response", status_code=status.HTTP_200_OK)
async def update_session_with_response(session_id: str, response_text: str):
    """
    Update a session with the response.
    
    - **session_id**: ID of the session to update
    - **response_text**: Response to add to the session
    """
    try:
        # Kiểm tra kết nối MongoDB
        if not check_db_connection():
            logger.error("MongoDB connection failed when trying to update session response")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MongoDB connection failed"
            )
        
        # Update session in MongoDB
        result = update_session_response(session_id, response_text)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} not found"
            )
            
        return {"status": "success", "message": "Response added to session"}
    except PyMongoError as e:
        logger.error(f"MongoDB error updating session response: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MongoDB error: {str(e)}"
        )
    except HTTPException:
        # Re-throw HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating session response: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {str(e)}"
        )

@router.get("/history", response_model=HistoryResponse)
async def get_history(user_id: str, n: int = Query(3, ge=1, le=10)):
    """
    Get user history for a specific user.
    
    - **user_id**: User's ID from Telegram
    - **n**: Number of most recent interactions to return (default: 3, min: 1, max: 10)
    """
    try:
        # Kiểm tra kết nối MongoDB
        if not check_db_connection():
            logger.error("MongoDB connection failed when trying to get user history")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MongoDB connection failed"
            )
        
        # Get user history from MongoDB
        history_data = get_user_history(user_id=user_id, n=n)
        
        # Convert to response model
        return HistoryResponse(history=history_data)
    except PyMongoError as e:
        logger.error(f"MongoDB error getting user history: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MongoDB error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting user history: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user history: {str(e)}"
        )

@router.get("/health")
async def health_check():
    """
    Check health of MongoDB connection.
    """
    try:
        # Kiểm tra kết nối MongoDB
        is_connected = check_db_connection()
        
        if not is_connected:
            return {
                "status": "unhealthy", 
                "message": "MongoDB connection failed", 
                "timestamp": datetime.now().isoformat()
            }
            
        return {
            "status": "healthy", 
            "message": "MongoDB connection is working", 
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        logger.error(traceback.format_exc())
        return {
            "status": "error", 
            "message": f"MongoDB health check error: {str(e)}", 
            "timestamp": datetime.now().isoformat()
        }

@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """
    Lấy thông tin session từ MongoDB theo session_id.
    
    - **session_id**: ID của session cần lấy
    """
    try:
        # Kiểm tra kết nối MongoDB
        if not check_db_connection():
            logger.error("MongoDB connection failed when trying to get session")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MongoDB connection failed"
            )
        
        # Lấy thông tin từ MongoDB
        session_data = session_collection.find_one({"session_id": session_id})
        
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session with ID {session_id} not found"
            )
            
        # Chuyển _id thành string để có thể JSON serialize
        if "_id" in session_data:
            session_data["_id"] = str(session_data["_id"])
            
        return session_data
    except PyMongoError as e:
        logger.error(f"MongoDB error getting session: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MongoDB error: {str(e)}"
        )
    except HTTPException:
        # Re-throw HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting session: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}"
        ) 