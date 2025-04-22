from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any
import logging
import traceback
from datetime import datetime
from sqlalchemy import text, inspect
import os
from dotenv import load_dotenv

from app.database.postgresql import get_db
from app.database.models import FAQItem, EmergencyItem, EventItem
from pydantic import BaseModel, Field, ConfigDict
from app.utils.cache import get_cache

# Load env variables
load_dotenv()

# Get cache settings
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 minutes by default

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/postgres",
    tags=["PostgreSQL"],
)

# --- Pydantic models for request/response ---

# FAQ models
class FAQBase(BaseModel):
    question: str
    answer: str
    is_active: bool = True

class FAQCreate(FAQBase):
    pass

class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    is_active: Optional[bool] = None

class FAQResponse(FAQBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    # Sử dụng ConfigDict thay vì class Config cho Pydantic V2
    model_config = ConfigDict(from_attributes=True)

# Emergency contact models
class EmergencyBase(BaseModel):
    name: str
    phone_number: str
    description: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    priority: int = 0
    is_active: bool = True

class EmergencyCreate(EmergencyBase):
    pass

class EmergencyUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None

class EmergencyResponse(EmergencyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    # Sử dụng ConfigDict thay vì class Config cho Pydantic V2
    model_config = ConfigDict(from_attributes=True)

# Event models
class EventBase(BaseModel):
    name: str
    description: str
    address: str
    location: Optional[str] = None
    date_start: datetime
    date_end: Optional[datetime] = None
    price: Optional[List[dict]] = None
    is_active: bool = True
    featured: bool = False

class EventCreate(EventBase):
    pass

class EventUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    price: Optional[List[dict]] = None
    is_active: Optional[bool] = None
    featured: Optional[bool] = None

class EventResponse(EventBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    # Sử dụng ConfigDict thay vì class Config cho Pydantic V2
    model_config = ConfigDict(from_attributes=True)

# --- FAQ endpoints ---

@router.get("/faq", response_model=List[FAQResponse])
async def get_faqs(
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get all FAQ items.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    """
    try:
        # Tạo cache key từ các tham số
        cache_key = f"faqs:{skip}:{limit}:{active_only}"
        cache = get_cache()
        
        # Thử lấy từ cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for FAQs: {cache_key}")
            return cached_result
        
        # Log detailed connection info
        logger.info(f"Cache miss, fetching FAQs from database with skip={skip}, limit={limit}, active_only={active_only}")
        
        # Check if the FAQItem table exists
        inspector = inspect(db.bind)
        if not inspector.has_table("faq_item"):
            logger.error("The faq_item table does not exist in the database")
            raise HTTPException(status_code=500, detail="Table 'faq_item' does not exist")
        
        # Log table columns
        columns = inspector.get_columns("faq_item")
        logger.info(f"faq_item table columns: {[c['name'] for c in columns]}")
        
        # Query the FAQs with detailed logging
        query = db.query(FAQItem)
        if active_only:
            query = query.filter(FAQItem.is_active == True)
        
        # Try direct SQL to debug
        try:
            test_result = db.execute(text("SELECT COUNT(*) FROM faq_item")).scalar()
            logger.info(f"SQL test query succeeded, found {test_result} FAQ items")
        except Exception as sql_error:
            logger.error(f"SQL test query failed: {sql_error}")
        
        # Execute the ORM query
        faqs = query.offset(skip).limit(limit).all()
        logger.info(f"Successfully fetched {len(faqs)} FAQ items")
        
        # Check what we're returning
        for i, faq in enumerate(faqs[:3]):  # Log the first 3 items
            logger.info(f"FAQ item {i+1}: id={faq.id}, question={faq.question[:30]}...")
        
        # Convert SQLAlchemy models to Pydantic models - updated for Pydantic v2
        result = [FAQResponse.model_validate(faq, from_attributes=True) for faq in faqs]
        
        # Lưu kết quả vào cache
        cache.set(cache_key, result, ttl=CACHE_TTL_SECONDS)
        logger.debug(f"Cached FAQs result with key: {cache_key}")
        
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_faqs: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in get_faqs: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.post("/faq", response_model=FAQResponse)
async def create_faq(
    faq: FAQCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new FAQ item.
    
    - **question**: Question text
    - **answer**: Answer text
    - **is_active**: Whether the FAQ is active (default: True)
    """
    try:
        # Sử dụng model_dump thay vì dict
        db_faq = FAQItem(**faq.model_dump())
        db.add(db_faq)
        db.commit()
        db.refresh(db_faq)
        
        # Xóa các cache key liên quan đến FAQ để đảm bảo dữ liệu luôn mới
        cache = get_cache()
        # Xóa tất cả các cache key bắt đầu bằng "faqs:"
        for key in list(cache.cache.keys()):
            if key.startswith("faqs:"):
                cache.delete(key)
        
        logger.debug("Cleared FAQ cache after creating new item")
        
        return FAQResponse.model_validate(db_faq, from_attributes=True)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create FAQ item")

@router.get("/faq/{faq_id}", response_model=FAQResponse)
async def get_faq(
    faq_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get a single FAQ item by ID.
    
    - **faq_id**: ID of the FAQ item to retrieve
    """
    try:
        # Tạo cache key
        cache_key = f"faq:{faq_id}"
        cache = get_cache()
        
        # Thử lấy từ cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for FAQ item: {faq_id}")
            return cached_result
        
        # Không có trong cache, truy vấn từ database
        logger.debug(f"Cache miss for FAQ item: {faq_id}")
        
        faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
        if faq is None:
            raise HTTPException(status_code=404, detail=f"FAQ with ID {faq_id} not found")
        
        result = FAQResponse.model_validate(faq, from_attributes=True)
        
        # Lưu kết quả vào cache
        cache.set(cache_key, result, ttl=CACHE_TTL_SECONDS)
        logger.debug(f"Cached FAQ item with ID: {faq_id}")
        
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/faq/{faq_id}", response_model=FAQResponse)
async def update_faq(
    faq_id: int = Path(..., gt=0),
    faq_update: FAQUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update an existing FAQ item.
    
    - **faq_id**: ID of the FAQ item to update
    - **question**: Updated question text (optional)
    - **answer**: Updated answer text (optional)
    - **is_active**: Updated active status (optional)
    """
    try:
        # Cập nhật trong database
        faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
        if faq is None:
            raise HTTPException(status_code=404, detail=f"FAQ with ID {faq_id} not found")
        
        # Cập nhật các trường từ faq_update nếu không phải là None
        update_data = faq_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(faq, key, value)
        
        db.add(faq)
        db.commit()
        db.refresh(faq)
        
        # Xóa các cache key liên quan
        cache = get_cache()
        # Xóa cache cho item riêng lẻ
        cache.delete(f"faq:{faq_id}")
        # Xóa tất cả các cache key bắt đầu bằng "faqs:" (danh sách FAQ)
        for key in list(cache.cache.keys()):
            if key.startswith("faqs:"):
                cache.delete(key)
        
        logger.debug(f"Cleared FAQ cache after updating item with ID: {faq_id}")
        
        return FAQResponse.model_validate(faq, from_attributes=True)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/faq/{faq_id}", response_model=dict)
async def delete_faq(
    faq_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete an FAQ item.
    
    - **faq_id**: ID of the FAQ item to delete
    """
    try:
        faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
        if faq is None:
            raise HTTPException(status_code=404, detail=f"FAQ with ID {faq_id} not found")
        
        db.delete(faq)
        db.commit()
        
        # Xóa các cache key liên quan
        cache = get_cache()
        # Xóa cache cho item riêng lẻ
        cache.delete(f"faq:{faq_id}")
        # Xóa tất cả các cache key bắt đầu bằng "faqs:" (danh sách FAQ)
        for key in list(cache.cache.keys()):
            if key.startswith("faqs:"):
                cache.delete(key)
        
        logger.debug(f"Cleared FAQ cache after deleting item with ID: {faq_id}")
        
        return {"message": f"FAQ with ID {faq_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# --- Emergency contact endpoints ---

@router.get("/emergency", response_model=List[EmergencyResponse])
async def get_emergency_contacts(
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get all emergency contacts.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    """
    try:
        # Tạo cache key từ các tham số
        cache_key = f"emergency:{skip}:{limit}:{active_only}"
        cache = get_cache()
        
        # Thử lấy từ cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for emergency contacts: {cache_key}")
            return cached_result
        
        # Không có trong cache, truy vấn từ database
        logger.debug(f"Cache miss for emergency contacts: {cache_key}")
        
        query = db.query(EmergencyItem)
        if active_only:
            query = query.filter(EmergencyItem.is_active == True)
        
        query = query.order_by(EmergencyItem.priority.desc())
        emergency_contacts = query.offset(skip).limit(limit).all()
        
        result = [EmergencyResponse.model_validate(contact, from_attributes=True) for contact in emergency_contacts]
        
        # Lưu kết quả vào cache
        cache.set(cache_key, result, ttl=CACHE_TTL_SECONDS)
        logger.debug(f"Cached emergency contacts with key: {cache_key}")
        
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/emergency/{emergency_id}", response_model=EmergencyResponse)
async def get_emergency_contact(
    emergency_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get a single emergency contact by ID.
    
    - **emergency_id**: ID of the emergency contact to retrieve
    """
    try:
        # Tạo cache key
        cache_key = f"emergency:{emergency_id}"
        cache = get_cache()
        
        # Thử lấy từ cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for emergency contact: {emergency_id}")
            return cached_result
        
        # Không có trong cache, truy vấn từ database
        logger.debug(f"Cache miss for emergency contact: {emergency_id}")
        
        contact = db.query(EmergencyItem).filter(EmergencyItem.id == emergency_id).first()
        if contact is None:
            raise HTTPException(status_code=404, detail=f"Emergency contact with ID {emergency_id} not found")
        
        result = EmergencyResponse.model_validate(contact, from_attributes=True)
        
        # Lưu kết quả vào cache
        cache.set(cache_key, result, ttl=CACHE_TTL_SECONDS)
        logger.debug(f"Cached emergency contact with ID: {emergency_id}")
        
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# --- Event endpoints ---

@router.get("/events", response_model=List[EventResponse])
async def get_events(
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    featured_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get all events.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    - **featured_only**: If true, only return featured items
    """
    try:
        # Tạo cache key từ các tham số
        cache_key = f"events:{skip}:{limit}:{active_only}:{featured_only}"
        cache = get_cache()
        
        # Thử lấy từ cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for events: {cache_key}")
            return cached_result
        
        # Không có trong cache, truy vấn từ database
        logger.debug(f"Cache miss for events: {cache_key}")
        
        query = db.query(EventItem)
        
        # Apply filters
        if active_only:
            query = query.filter(EventItem.is_active == True)
        if featured_only:
            query = query.filter(EventItem.featured == True)
        
        # Order by date (upcoming events first)
        query = query.order_by(EventItem.date_start.asc())
        
        # Get results
        events = query.offset(skip).limit(limit).all()
        
        result = [EventResponse.model_validate(event, from_attributes=True) for event in events]
        
        # Lưu kết quả vào cache
        cache.set(cache_key, result, ttl=CACHE_TTL_SECONDS)
        logger.debug(f"Cached events with key: {cache_key}")
        
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get a single event by ID.
    
    - **event_id**: ID of the event to retrieve
    """
    try:
        # Tạo cache key
        cache_key = f"event:{event_id}"
        cache = get_cache()
        
        # Thử lấy từ cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for event: {event_id}")
            return cached_result
        
        # Không có trong cache, truy vấn từ database
        logger.debug(f"Cache miss for event: {event_id}")
        
        event = db.query(EventItem).filter(EventItem.id == event_id).first()
        if event is None:
            raise HTTPException(status_code=404, detail=f"Event with ID {event_id} not found")
        
        result = EventResponse.model_validate(event, from_attributes=True)
        
        # Lưu kết quả vào cache
        cache.set(cache_key, result, ttl=CACHE_TTL_SECONDS)
        logger.debug(f"Cached event with ID: {event_id}")
        
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/events/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: int = Path(..., gt=0),
    event_update: EventUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update an existing event.
    
    - **event_id**: ID of the event to update
    - **event_update**: Data to update
    """
    try:
        event = db.query(EventItem).filter(EventItem.id == event_id).first()
        if event is None:
            raise HTTPException(status_code=404, detail=f"Event with ID {event_id} not found")
        
        # Cập nhật các trường từ event_update nếu không phải là None
        update_data = event_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(event, key, value)
        
        db.add(event)
        db.commit()
        db.refresh(event)
        
        # Xóa các cache key liên quan
        cache = get_cache()
        # Xóa cache cho item riêng lẻ
        cache.delete(f"event:{event_id}")
        # Xóa tất cả các cache key bắt đầu bằng "events:" (danh sách events)
        for key in list(cache.cache.keys()):
            if key.startswith("events:"):
                cache.delete(key)
        
        logger.debug(f"Cleared events cache after updating item with ID: {event_id}")
        
        return EventResponse.model_validate(event, from_attributes=True)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/events/{event_id}", response_model=dict)
async def delete_event(
    event_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete an event.
    
    - **event_id**: ID of the event to delete
    """
    try:
        event = db.query(EventItem).filter(EventItem.id == event_id).first()
        if event is None:
            raise HTTPException(status_code=404, detail=f"Event with ID {event_id} not found")
        
        db.delete(event)
        db.commit()
        
        # Xóa các cache key liên quan
        cache = get_cache()
        # Xóa cache cho item riêng lẻ
        cache.delete(f"event:{event_id}")
        # Xóa tất cả các cache key bắt đầu bằng "events:" (danh sách events)
        for key in list(cache.cache.keys()):
            if key.startswith("events:"):
                cache.delete(key)
        
        logger.debug(f"Cleared events cache after deleting item with ID: {event_id}")
        
        return {"message": f"Event with ID {event_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Health check endpoint
@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Check health of PostgreSQL connection.
    """
    try:
        # Perform a simple database query to check health
        # Use text() to wrap the SQL query for SQLAlchemy 2.0 compatibility
        db.execute(text("SELECT 1")).first()
        return {"status": "healthy", "message": "PostgreSQL connection is working", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"PostgreSQL connection failed: {str(e)}") 