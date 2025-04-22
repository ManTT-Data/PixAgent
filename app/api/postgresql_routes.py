import logging
import json
import traceback
from datetime import datetime, timedelta, timezone
import time
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any
import logging
import traceback
from datetime import datetime
from sqlalchemy import text, inspect, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import desc, func
from cachetools import TTLCache

from app.database.postgresql import get_db
from app.database.models import FAQItem, EmergencyItem, EventItem, AboutPixity, SolanaSummit, DaNangBucketList
from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/postgres",
    tags=["PostgreSQL"],
)

# Initialize caches for frequently used data
# Cache for 5 minutes (300 seconds)
faqs_cache = TTLCache(maxsize=1, ttl=300)
emergencies_cache = TTLCache(maxsize=1, ttl=300)
events_cache = TTLCache(maxsize=10, ttl=300)  # Cache for different page sizes
about_pixity_cache = TTLCache(maxsize=1, ttl=300)
solana_summit_cache = TTLCache(maxsize=1, ttl=300)
danang_bucket_list_cache = TTLCache(maxsize=1, ttl=300)

# --- Pydantic models for request/response ---

# Information models
class InfoContentBase(BaseModel):
    content: str

class InfoContentCreate(InfoContentBase):
    pass

class InfoContentUpdate(InfoContentBase):
    pass

class InfoContentResponse(InfoContentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

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
    
    # Use class Config for Pydantic v1
    class Config:
        orm_mode = True

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
    
    # Use class Config for Pydantic v1
    class Config:
        orm_mode = True

# Event models
class EventBase(BaseModel):
    name: str
    description: str
    address: str
    location: Optional[str] = None
    date_start: datetime
    date_end: Optional[datetime] = None
    price: Optional[List[dict]] = None
    url: Optional[str] = None
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
    url: Optional[str] = None
    is_active: Optional[bool] = None
    featured: Optional[bool] = None

class EventResponse(EventBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    # Use class Config for Pydantic v1
    class Config:
        orm_mode = True

# --- Batch operations for better performance ---

class BatchEventCreate(BaseModel):
    events: List[EventCreate]

class BatchUpdateResult(BaseModel):
    success_count: int
    failed_ids: List[int] = []
    message: str

# --- FAQ endpoints ---

@router.get("/faq", response_model=List[FAQResponse])
async def get_faqs(
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get all FAQ items.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    - **use_cache**: If true, use cached results when available
    """
    try:
        # Generate cache key based on query parameters
        cache_key = f"faqs_{skip}_{limit}_{active_only}"
        
        # Try to get from cache if caching is enabled
        if use_cache:
            cached_result = faqs_cache.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for {cache_key}")
                return cached_result
        
        # Build query directly without excessive logging or inspection
        query = db.query(FAQItem)
        
        # Add filter if needed
        if active_only:
            query = query.filter(FAQItem.is_active == True)
        
        # Get total count for pagination
        count_query = query.with_entities(func.count(FAQItem.id))
        total_count = count_query.scalar()
        
        # Execute query with pagination
        faqs = query.offset(skip).limit(limit).all()
        
        # Convert to Pydantic models
        result = [FAQResponse.from_orm(faq) for faq in faqs]
        
        # Store in cache if caching is enabled
        if use_cache:
            faqs_cache.set(cache_key, result)
            
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
        # Create new FAQ item
        db_faq = FAQItem(**faq.dict())
        db.add(db_faq)
        db.commit()
        db.refresh(db_faq)
        
        # Invalidate FAQ cache after creating a new item
        faqs_cache.clear()
        
        # Convert to Pydantic model
        return FAQResponse.from_orm(db_faq)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in create_faq: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/faq/{faq_id}", response_model=FAQResponse)
async def get_faq(
    faq_id: int = Path(..., gt=0),
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get a specific FAQ item by ID.
    
    - **faq_id**: ID of the FAQ item
    - **use_cache**: If true, use cached results when available
    """
    try:
        # Generate cache key
        cache_key = f"faq_{faq_id}"
        
        # Try to get from cache if caching is enabled
        if use_cache:
            cached_result = faqs_cache.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for {cache_key}")
                return cached_result
        
        # Use direct SQL query for better performance on single item lookup
        stmt = text("SELECT * FROM faq_item WHERE id = :id")
        result = db.execute(stmt, {"id": faq_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="FAQ item not found")
        
        # Create a FAQItem model instance manually
        faq = FAQItem()
        for key, value in result._mapping.items():
            if hasattr(faq, key):
                setattr(faq, key, value)
                
        # Convert to Pydantic model
        response = FAQResponse.from_orm(faq)
        
        # Store in cache if caching is enabled
        if use_cache:
            faqs_cache.set(cache_key, response)
            
        return response
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_faq: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/faq/{faq_id}", response_model=FAQResponse)
async def update_faq(
    faq_id: int = Path(..., gt=0),
    faq_update: FAQUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update a specific FAQ item.
    
    - **faq_id**: ID of the FAQ item to update
    - **question**: New question text (optional)
    - **answer**: New answer text (optional)
    - **is_active**: New active status (optional)
    """
    try:
        # Check if FAQ exists
        faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ item not found")
        
        # Update fields with optimized dict handling
        update_data = faq_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(faq, key, value)
            
        # Commit changes
        db.commit()
        db.refresh(faq)
        
        # Invalidate specific cache entries
        faqs_cache.delete(f"faq_{faq_id}")
        faqs_cache.clear()  # Clear all list caches
        
        # Convert to Pydantic model
        return FAQResponse.from_orm(faq)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in update_faq: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/faq/{faq_id}", response_model=dict)
async def delete_faq(
    faq_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete a specific FAQ item.
    
    - **faq_id**: ID of the FAQ item to delete
    """
    try:
        # Use optimized query with proper error handling
        result = db.execute(
            text("DELETE FROM faq_item WHERE id = :id RETURNING id"),
            {"id": faq_id}
        ).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="FAQ item not found")
        
        db.commit()
        
        # Invalidate cache entries
        faqs_cache.delete(f"faq_{faq_id}")
        faqs_cache.clear()  # Clear all list caches
        
        return {"status": "success", "message": f"FAQ item {faq_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in delete_faq: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# --- Emergency endpoints ---

@router.get("/emergency", response_model=List[EmergencyResponse])
async def get_emergency_contacts(
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get all emergency contacts.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    - **use_cache**: If true, use cached results when available
    """
    try:
        # Generate cache key based on query parameters
        cache_key = f"emergency_{skip}_{limit}_{active_only}"
        
        # Try to get from cache if caching is enabled
        if use_cache:
            cached_result = emergencies_cache.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for {cache_key}")
                return cached_result
                
        # Build query directly without excessive inspection and logging
        query = db.query(EmergencyItem)
        
        # Add filters if needed
        if active_only:
            query = query.filter(EmergencyItem.is_active == True)
        
        # Get total count for pagination info
        count_query = query.with_entities(func.count(EmergencyItem.id))
        total_count = count_query.scalar()
        
        # Order by priority for proper sorting
        emergency_contacts = query.order_by(EmergencyItem.priority.desc()).offset(skip).limit(limit).all()
        
        # Convert to Pydantic models efficiently
        result = [EmergencyResponse.from_orm(contact) for contact in emergency_contacts]
        
        # Store in cache if caching is enabled
        if use_cache:
            emergencies_cache.set(cache_key, result)
            
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_emergency_contacts: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in get_emergency_contacts: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.post("/emergency", response_model=EmergencyResponse)
async def create_emergency_contact(
    emergency: EmergencyCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new emergency contact.
    
    - **name**: Contact name
    - **phone_number**: Phone number
    - **description**: Description (optional)
    - **address**: Address (optional)
    - **location**: Location coordinates (optional)
    - **priority**: Priority order (default: 0)
    - **is_active**: Whether the contact is active (default: True)
    """
    try:
        db_emergency = EmergencyItem(**emergency.dict())
        db.add(db_emergency)
        db.commit()
        db.refresh(db_emergency)
        
        # Invalidate emergency cache after creating a new item
        emergencies_cache.clear()
        
        # Convert SQLAlchemy model to Pydantic model before returning
        result = EmergencyResponse.from_orm(db_emergency)
        return result
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in create_emergency_contact: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/emergency/{emergency_id}", response_model=EmergencyResponse)
async def get_emergency_contact(
    emergency_id: int = Path(..., gt=0),
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get a specific emergency contact by ID.
    
    - **emergency_id**: ID of the emergency contact
    - **use_cache**: If true, use cached results when available
    """
    try:
        # Generate cache key
        cache_key = f"emergency_{emergency_id}"
        
        # Try to get from cache if caching is enabled
        if use_cache:
            cached_result = emergencies_cache.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for {cache_key}")
                return cached_result
                
        # Use direct SQL query for better performance on single item lookup
        stmt = text("SELECT * FROM emergency_item WHERE id = :id")
        result = db.execute(stmt, {"id": emergency_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Emergency contact not found")
        
        # Create an EmergencyItem model instance manually
        emergency = EmergencyItem()
        for key, value in result._mapping.items():
            if hasattr(emergency, key):
                setattr(emergency, key, value)
                
        # Convert to Pydantic model
        response = EmergencyResponse.from_orm(emergency)
        
        # Store in cache if caching is enabled
        if use_cache:
            emergencies_cache.set(cache_key, response)
            
        return response
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_emergency_contact: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/emergency/{emergency_id}", response_model=EmergencyResponse)
async def update_emergency_contact(
    emergency_id: int = Path(..., gt=0),
    emergency_update: EmergencyUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update a specific emergency contact.
    
    - **emergency_id**: ID of the emergency contact to update
    - **name**: New name (optional)
    - **phone_number**: New phone number (optional)
    - **description**: New description (optional)
    - **address**: New address (optional)
    - **location**: New location coordinates (optional)
    - **priority**: New priority order (optional)
    - **is_active**: New active status (optional)
    """
    try:
        emergency = db.query(EmergencyItem).filter(EmergencyItem.id == emergency_id).first()
        if not emergency:
            raise HTTPException(status_code=404, detail="Emergency contact not found")
        
        # Update fields if provided
        update_data = emergency_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(emergency, key, value)
            
        db.commit()
        db.refresh(emergency)
        
        # Invalidate specific cache entries
        emergencies_cache.delete(f"emergency_{emergency_id}")
        emergencies_cache.clear()  # Clear all list caches
        
        # Convert to Pydantic model
        return EmergencyResponse.from_orm(emergency)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in update_emergency_contact: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/emergency/{emergency_id}", response_model=dict)
async def delete_emergency_contact(
    emergency_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete a specific emergency contact.
    
    - **emergency_id**: ID of the emergency contact to delete
    """
    try:
        # Use optimized direct SQL with RETURNING for better performance
        result = db.execute(
            text("DELETE FROM emergency_item WHERE id = :id RETURNING id"),
            {"id": emergency_id}
        ).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Emergency contact not found")
        
        db.commit()
        
        # Invalidate cache entries
        emergencies_cache.delete(f"emergency_{emergency_id}")
        emergencies_cache.clear()  # Clear all list caches
        
        return {"status": "success", "message": f"Emergency contact {emergency_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in delete_emergency_contact: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# --- Event endpoints ---

@router.get("/events", response_model=List[EventResponse])
async def get_events(
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    featured_only: bool = False,
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get all events.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    - **featured_only**: If true, only return featured items
    - **use_cache**: If true, use cached results when available
    """
    try:
        # Generate cache key based on query parameters
        cache_key = f"events_{skip}_{limit}_{active_only}_{featured_only}"
        
        # Try to get from cache if caching is enabled
        if use_cache:
            cached_result = events_cache.get(cache_key)
            if cached_result:
                return cached_result
        
        # Build query directly without excessive inspection and logging
        query = db.query(EventItem)
        
        # Add filters if needed
        if active_only:
            query = query.filter(EventItem.is_active == True)
        if featured_only:
            query = query.filter(EventItem.featured == True)
        
        # To improve performance, first fetch just IDs with COUNT
        count_query = query.with_entities(func.count(EventItem.id))
        total_count = count_query.scalar()
        
        # Now get the actual data with pagination
        events = query.order_by(EventItem.date_start.desc()).offset(skip).limit(limit).all()
        
        # Convert to Pydantic models efficiently
        result = [EventResponse.from_orm(event) for event in events]
        
        # Store in cache if caching is enabled (30 seconds TTL for events list)
        if use_cache:
            events_cache.set(cache_key, result, ttl=30)
            
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_events: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in get_events: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.post("/events", response_model=EventResponse)
async def create_event(
    event: EventCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new event.
    
    - **name**: Event name
    - **description**: Event description
    - **address**: Event address
    - **location**: Location coordinates (optional)
    - **date_start**: Start date and time
    - **date_end**: End date and time (optional)
    - **price**: Price information (optional JSON object)
    - **is_active**: Whether the event is active (default: True)
    - **featured**: Whether the event is featured (default: False)
    """
    try:
        db_event = EventItem(**event.dict())
        db.add(db_event)
        db.commit()
        db.refresh(db_event)
        
        # Invalidate relevant caches on create
        events_cache.clear()
        
        # Convert SQLAlchemy model to Pydantic model before returning
        result = EventResponse.from_orm(db_event)
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in create_event: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: int = Path(..., gt=0),
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get a specific event by ID.
    
    - **event_id**: ID of the event
    - **use_cache**: If true, use cached results when available
    """
    try:
        # Generate cache key
        cache_key = f"event_{event_id}"
        
        # Try to get from cache if caching is enabled
        if use_cache:
            cached_result = events_cache.get(cache_key)
            if cached_result:
                return cached_result
        
        # Use direct SQL query for better performance on single item lookup
        # This avoids SQLAlchemy overhead and takes advantage of primary key lookup
        stmt = text("SELECT * FROM event_item WHERE id = :id")
        result = db.execute(stmt, {"id": event_id}).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Create an EventItem model instance manually from the result
        event = EventItem()
        for key, value in result._mapping.items():
            if hasattr(event, key):
                setattr(event, key, value)
                
        # Convert SQLAlchemy model to Pydantic model
        response = EventResponse.from_orm(event)
        
        # Store in cache if caching is enabled (60 seconds TTL for single event)
        if use_cache:
            events_cache.set(cache_key, response, ttl=60)
            
        return response
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_event: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/events/{event_id}", response_model=EventResponse)
def update_event(
    event_id: int, 
    event: EventUpdate, 
    db: Session = Depends(get_db)
):
    """Update an existing event."""
    try:
        db_event = db.query(EventItem).filter(EventItem.id == event_id).first()
        if not db_event:
            raise HTTPException(status_code=404, detail="Event not found")
            
        # Update event fields
        for key, value in event.dict(exclude_unset=True).items():
            setattr(db_event, key, value)
            
        db.commit()
        db.refresh(db_event)
        
        # Invalidate specific cache entries
        events_cache.delete(f"event_{event_id}")
        events_cache.clear()  # Clear all list caches
        
        # Convert SQLAlchemy model to Pydantic model before returning
        result = EventResponse.from_orm(db_event)
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in update_event: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/events/{event_id}", response_model=dict)
async def delete_event(
    event_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """Delete a specific event."""
    try:
        event = db.query(EventItem).filter(EventItem.id == event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        db.delete(event)
        db.commit()
        
        # Invalidate cache entries
        events_cache.delete(f"event_{event_id}")
        events_cache.clear()  # Clear all list caches
        
        return {"status": "success", "message": f"Event {event_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete event")

# --- Batch operations for better performance ---

@router.post("/events/batch", response_model=List[EventResponse])
async def batch_create_events(
    batch: BatchEventCreate,
    db: Session = Depends(get_db)
):
    """
    Create multiple events in a single database transaction.
    
    This is much more efficient than creating events one at a time with separate API calls.
    """
    try:
        db_events = []
        for event_data in batch.events:
            db_event = EventItem(**event_data.dict())
            db.add(db_event)
            db_events.append(db_event)
        
        # Commit all events in a single transaction
        db.commit()
        
        # Refresh all events to get their IDs and other generated fields
        for db_event in db_events:
            db.refresh(db_event)
        
        # Convert SQLAlchemy models to Pydantic models
        result = [EventResponse.from_orm(event) for event in db_events]
        return result
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in batch_create_events: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/events/batch-update-status", response_model=BatchUpdateResult)
async def batch_update_event_status(
    event_ids: List[int] = Body(..., embed=True),
    is_active: bool = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Update the active status of multiple events at once.
    
    This is much more efficient than updating events one at a time.
    """
    try:
        if not event_ids:
            raise HTTPException(status_code=400, detail="No event IDs provided")
        
        # Prepare the update statement
        stmt = text("""
            UPDATE event_item 
            SET is_active = :is_active, updated_at = NOW()
            WHERE id = ANY(:event_ids)
            RETURNING id
        """)
        
        # Execute the update in a single query
        result = db.execute(stmt, {"is_active": is_active, "event_ids": event_ids})
        updated_ids = [row[0] for row in result]
        
        # Commit the transaction
        db.commit()
        
        # Determine which IDs weren't found
        failed_ids = [id for id in event_ids if id not in updated_ids]
        
        return BatchUpdateResult(
            success_count=len(updated_ids),
            failed_ids=failed_ids,
            message=f"Updated {len(updated_ids)} events" if updated_ids else "No events were updated"
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in batch_update_event_status: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/events/batch", response_model=BatchUpdateResult)
async def batch_delete_events(
    event_ids: List[int] = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Delete multiple events at once.
    
    This is much more efficient than deleting events one at a time with separate API calls.
    """
    try:
        if not event_ids:
            raise HTTPException(status_code=400, detail="No event IDs provided")
        
        # Prepare and execute the delete statement with RETURNING to get deleted IDs
        stmt = text("""
            DELETE FROM event_item
            WHERE id = ANY(:event_ids)
            RETURNING id
        """)
        
        result = db.execute(stmt, {"event_ids": event_ids})
        deleted_ids = [row[0] for row in result]
        
        # Commit the transaction
        db.commit()
        
        # Determine which IDs weren't found
        failed_ids = [id for id in event_ids if id not in deleted_ids]
        
        return BatchUpdateResult(
            success_count=len(deleted_ids),
            failed_ids=failed_ids,
            message=f"Deleted {len(deleted_ids)} events" if deleted_ids else "No events were deleted"
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in batch_delete_events: {e}")
        logger.error(traceback.format_exc())
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

# Add BatchFAQCreate class to model definitions
class BatchFAQCreate(BaseModel):
    faqs: List[FAQCreate]

# Add after delete_faq endpoint
@router.post("/faqs/batch", response_model=List[FAQResponse])
async def batch_create_faqs(
    batch: BatchFAQCreate,
    db: Session = Depends(get_db)
):
    """
    Create multiple FAQ items in a single database transaction.
    
    This is much more efficient than creating FAQ items one at a time with separate API calls.
    """
    try:
        db_faqs = []
        for faq_data in batch.faqs:
            db_faq = FAQItem(**faq_data.dict())
            db.add(db_faq)
            db_faqs.append(db_faq)
        
        # Commit all FAQ items in a single transaction
        db.commit()
        
        # Refresh all FAQ items to get their IDs and other generated fields
        for db_faq in db_faqs:
            db.refresh(db_faq)
        
        # Invalidate FAQ cache
        faqs_cache.clear()
        
        # Convert SQLAlchemy models to Pydantic models
        result = [FAQResponse.from_orm(faq) for faq in db_faqs]
        return result
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in batch_create_faqs: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/faqs/batch-update-status", response_model=BatchUpdateResult)
async def batch_update_faq_status(
    faq_ids: List[int] = Body(..., embed=True),
    is_active: bool = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Update the active status of multiple FAQ items at once.
    
    This is much more efficient than updating FAQ items one at a time.
    """
    try:
        if not faq_ids:
            raise HTTPException(status_code=400, detail="No FAQ IDs provided")
        
        # Prepare the update statement
        stmt = text("""
            UPDATE faq_item 
            SET is_active = :is_active, updated_at = NOW()
            WHERE id = ANY(:faq_ids)
            RETURNING id
        """)
        
        # Execute the update in a single query
        result = db.execute(stmt, {"is_active": is_active, "faq_ids": faq_ids})
        updated_ids = [row[0] for row in result]
        
        # Commit the transaction
        db.commit()
        
        # Determine which IDs weren't found
        failed_ids = [id for id in faq_ids if id not in updated_ids]
        
        # Invalidate FAQ cache
        faqs_cache.clear()
        
        return BatchUpdateResult(
            success_count=len(updated_ids),
            failed_ids=failed_ids,
            message=f"Updated {len(updated_ids)} FAQ items" if updated_ids else "No FAQ items were updated"
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in batch_update_faq_status: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/faqs/batch", response_model=BatchUpdateResult)
async def batch_delete_faqs(
    faq_ids: List[int] = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Delete multiple FAQ items at once.
    
    This is much more efficient than deleting FAQ items one at a time with separate API calls.
    """
    try:
        if not faq_ids:
            raise HTTPException(status_code=400, detail="No FAQ IDs provided")
        
        # Prepare and execute the delete statement with RETURNING to get deleted IDs
        stmt = text("""
            DELETE FROM faq_item
            WHERE id = ANY(:faq_ids)
            RETURNING id
        """)
        
        result = db.execute(stmt, {"faq_ids": faq_ids})
        deleted_ids = [row[0] for row in result]
        
        # Commit the transaction
        db.commit()
        
        # Determine which IDs weren't found
        failed_ids = [id for id in faq_ids if id not in deleted_ids]
        
        # Invalidate FAQ cache
        faqs_cache.clear()
        
        return BatchUpdateResult(
            success_count=len(deleted_ids),
            failed_ids=failed_ids,
            message=f"Deleted {len(deleted_ids)} FAQ items" if deleted_ids else "No FAQ items were deleted"
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in batch_delete_faqs: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Add BatchEmergencyCreate class to the Pydantic models section
class BatchEmergencyCreate(BaseModel):
    emergency_contacts: List[EmergencyCreate]

@router.post("/emergency/batch", response_model=List[EmergencyResponse])
async def batch_create_emergency_contacts(
    batch: BatchEmergencyCreate,
    db: Session = Depends(get_db)
):
    """
    Create multiple emergency contacts in a single database transaction.
    
    This is much more efficient than creating emergency contacts one at a time with separate API calls.
    """
    try:
        db_emergency_contacts = []
        for emergency_data in batch.emergency_contacts:
            db_emergency = EmergencyItem(**emergency_data.dict())
            db.add(db_emergency)
            db_emergency_contacts.append(db_emergency)
        
        # Commit all emergency contacts in a single transaction
        db.commit()
        
        # Refresh all items to get their IDs and other generated fields
        for db_emergency in db_emergency_contacts:
            db.refresh(db_emergency)
        
        # Invalidate emergency cache
        emergencies_cache.clear()
        
        # Convert SQLAlchemy models to Pydantic models
        result = [EmergencyResponse.from_orm(emergency) for emergency in db_emergency_contacts]
        return result
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in batch_create_emergency_contacts: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/emergency/batch-update-status", response_model=BatchUpdateResult)
async def batch_update_emergency_status(
    emergency_ids: List[int] = Body(..., embed=True),
    is_active: bool = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Update the active status of multiple emergency contacts at once.
    
    This is much more efficient than updating emergency contacts one at a time.
    """
    try:
        if not emergency_ids:
            raise HTTPException(status_code=400, detail="No emergency contact IDs provided")
        
        # Prepare the update statement
        stmt = text("""
            UPDATE emergency_item 
            SET is_active = :is_active, updated_at = NOW()
            WHERE id = ANY(:emergency_ids)
            RETURNING id
        """)
        
        # Execute the update in a single query
        result = db.execute(stmt, {"is_active": is_active, "emergency_ids": emergency_ids})
        updated_ids = [row[0] for row in result]
        
        # Commit the transaction
        db.commit()
        
        # Determine which IDs weren't found
        failed_ids = [id for id in emergency_ids if id not in updated_ids]
        
        # Invalidate emergency cache
        emergencies_cache.clear()
        
        return BatchUpdateResult(
            success_count=len(updated_ids),
            failed_ids=failed_ids,
            message=f"Updated {len(updated_ids)} emergency contacts" if updated_ids else "No emergency contacts were updated"
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in batch_update_emergency_status: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/emergency/batch", response_model=BatchUpdateResult)
async def batch_delete_emergency_contacts(
    emergency_ids: List[int] = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Delete multiple emergency contacts at once.
    
    This is much more efficient than deleting emergency contacts one at a time with separate API calls.
    """
    try:
        if not emergency_ids:
            raise HTTPException(status_code=400, detail="No emergency contact IDs provided")
        
        # Prepare and execute the delete statement with RETURNING to get deleted IDs
        stmt = text("""
            DELETE FROM emergency_item
            WHERE id = ANY(:emergency_ids)
            RETURNING id
        """)
        
        result = db.execute(stmt, {"emergency_ids": emergency_ids})
        deleted_ids = [row[0] for row in result]
        
        # Commit the transaction
        db.commit()
        
        # Determine which IDs weren't found
        failed_ids = [id for id in emergency_ids if id not in deleted_ids]
        
        # Invalidate emergency cache
        emergencies_cache.clear()
        
        return BatchUpdateResult(
            success_count=len(deleted_ids),
            failed_ids=failed_ids,
            message=f"Deleted {len(deleted_ids)} emergency contacts" if deleted_ids else "No emergency contacts were deleted"
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in batch_delete_emergency_contacts: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# --- About Pixity endpoints ---

@router.get("/about-pixity", response_model=InfoContentResponse)
async def get_about_pixity(
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get the About Pixity information.
    
    - **use_cache**: If true, use cached results when available
    """
    try:
        # Try to get from cache if caching is enabled
        if use_cache:
            cached_result = about_pixity_cache.get("about_pixity")
            if cached_result:
                logger.info("Cache hit for about_pixity")
                return cached_result
        
        # Get the first record (or create if none exists)
        about = db.query(AboutPixity).first()
        
        if not about:
            # Create default content if none exists
            about = AboutPixity(
                content="""PiXity is your smart, AI-powered local companion designed to help foreigners navigate life in any city of Vietnam with ease, starting with Da Nang. From finding late-night eats to handling visas, housing, and healthcare, PiXity bridges the gap in language, culture, and local know-how — so you can explore the city like a true insider.

PiXity is proudly built by PiX.teq, the tech team behind PiX — a multidisciplinary collective based in Da Nang.

X: x.com/pixity_bot
Instagram: instagram.com/pixity.aibot/
Tiktok: tiktok.com/@pixity.aibot"""
            )
            db.add(about)
            db.commit()
            db.refresh(about)
        
        # Convert to Pydantic model
        response = InfoContentResponse(
            id=about.id,
            content=about.content,
            created_at=about.created_at,
            updated_at=about.updated_at
        )
        
        # Store in cache if caching is enabled
        if use_cache:
            about_pixity_cache.set("about_pixity", response)
            
        return response
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_about_pixity: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/about-pixity", response_model=InfoContentResponse)
async def update_about_pixity(
    data: InfoContentUpdate,
    db: Session = Depends(get_db)
):
    """
    Update the About Pixity information.
    
    - **content**: New content text
    """
    try:
        # Get the first record (or create if none exists)
        about = db.query(AboutPixity).first()
        
        if not about:
            # Create new record if none exists
            about = AboutPixity(content=data.content)
            db.add(about)
        else:
            # Update existing record
            about.content = data.content
            
        db.commit()
        db.refresh(about)
        
        # Invalidate cache
        about_pixity_cache.clear()
        
        # Convert to Pydantic model
        response = InfoContentResponse(
            id=about.id,
            content=about.content,
            created_at=about.created_at,
            updated_at=about.updated_at
        )
        
        return response
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in update_about_pixity: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# --- Da Nang Bucket List Pydantic models ---
class DaNangBucketListBase(BaseModel):
    content: str

class DaNangBucketListResponse(DaNangBucketListBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True
        
class DaNangBucketListCreate(DaNangBucketListBase):
    pass

class DaNangBucketListUpdate(BaseModel):
    content: str

# --- Da Nang Bucket List Endpoints ---
@router.get("/danang-bucket-list", response_model=DaNangBucketListResponse)
async def get_danang_bucket_list(
    db: Session = Depends(get_db),
    use_cache: bool = True
):
    """
    Retrieve the Da Nang Bucket List information.
    If none exists, creates a default entry.
    """
    cache_key = "danang_bucket_list"
    
    # Try to get from cache if caching is enabled
    if use_cache and cache_key in danang_bucket_list_cache:
        cached_result = danang_bucket_list_cache[cache_key]
        logger.info(f"Cache hit for {cache_key}")
        return cached_result
    
    try:
        # Try to get the first bucket list entry
        db_bucket_list = db.query(DaNangBucketList).first()
        
        # If no entry exists, create a default one
        if not db_bucket_list:
            default_content = json.dumps({
                "title": "Da Nang Bucket List",
                "description": "Must-visit places and experiences in Da Nang",
                "items": [
                    {"name": "Ba Na Hills", "description": "Visit the famous Golden Bridge"},
                    {"name": "Marble Mountains", "description": "Explore caves and temples"},
                    {"name": "My Khe Beach", "description": "Relax at one of the most beautiful beaches in Vietnam"},
                    {"name": "Dragon Bridge", "description": "Watch the fire-breathing show on weekends"},
                    {"name": "Son Tra Peninsula", "description": "See the Lady Buddha statue and lookout point"}
                ]
            })
            
            new_bucket_list = DaNangBucketList(content=default_content)
            db.add(new_bucket_list)
            db.commit()
            db.refresh(new_bucket_list)
            db_bucket_list = new_bucket_list
            
        # Convert to Pydantic model
        response = DaNangBucketListResponse.from_orm(db_bucket_list)
        
        # Store in cache if caching is enabled
        if use_cache:
            danang_bucket_list_cache[cache_key] = response
            
        return response
        
    except SQLAlchemyError as e:
        error_msg = f"Database error in get_danang_bucket_list: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

@router.put("/danang-bucket-list", response_model=DaNangBucketListResponse)
async def update_danang_bucket_list(
    bucket_list_data: DaNangBucketListUpdate,
    db: Session = Depends(get_db)
):
    """
    Update the Da Nang Bucket List information.
    If none exists, creates a new entry.
    """
    try:
        # Try to get the first bucket list entry
        db_bucket_list = db.query(DaNangBucketList).first()
        
        # If no entry exists, create a new one
        if not db_bucket_list:
            db_bucket_list = DaNangBucketList(content=bucket_list_data.content)
            db.add(db_bucket_list)
        else:
            # Update existing entry
            db_bucket_list.content = bucket_list_data.content
            db_bucket_list.updated_at = datetime.utcnow()
            
        db.commit()
        db.refresh(db_bucket_list)
        
        # Clear cache
        if "danang_bucket_list" in danang_bucket_list_cache:
            del danang_bucket_list_cache["danang_bucket_list"]
        
        # Convert to Pydantic model
        return DaNangBucketListResponse.from_orm(db_bucket_list)
        
    except SQLAlchemyError as e:
        error_msg = f"Database error in update_danang_bucket_list: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

# --- Solana Summit Pydantic models ---
class SolanaSummitBase(BaseModel):
    content: str

class SolanaSummitResponse(SolanaSummitBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True
        
class SolanaSummitCreate(SolanaSummitBase):
    pass

class SolanaSummitUpdate(BaseModel):
    content: str

# --- Solana Summit Endpoints ---
@router.get("/solana-summit", response_model=SolanaSummitResponse)
async def get_solana_summit(
    db: Session = Depends(get_db),
    use_cache: bool = True
):
    """
    Retrieve the Solana Summit information.
    If none exists, creates a default entry.
    """
    cache_key = "solana_summit"
    
    # Try to get from cache if caching is enabled
    if use_cache and cache_key in solana_summit_cache:
        cached_result = solana_summit_cache[cache_key]
        logger.info(f"Cache hit for {cache_key}")
        return cached_result
    
    try:
        # Try to get the first solana summit entry
        db_solana_summit = db.query(SolanaSummit).first()
        
        # If no entry exists, create a default one
        if not db_solana_summit:
            default_content = json.dumps({
                "title": "Solana Summit Vietnam",
                "description": "Information about Solana Summit Vietnam event in Da Nang",
                "date": "2023-11-04T09:00:00+07:00",
                "location": "Hyatt Regency, Da Nang",
                "details": "The Solana Summit is a gathering of developers, entrepreneurs, and enthusiasts in the Solana ecosystem.",
                "agenda": [
                    {"time": "09:00", "activity": "Registration & Networking"},
                    {"time": "10:00", "activity": "Opening Keynote"},
                    {"time": "12:00", "activity": "Lunch Break"},
                    {"time": "13:30", "activity": "Developer Workshops"},
                    {"time": "17:00", "activity": "Closing Remarks & Networking"}
                ],
                "registration_url": "https://example.com/solana-summit-registration"
            })
            
            new_solana_summit = SolanaSummit(content=default_content)
            db.add(new_solana_summit)
            db.commit()
            db.refresh(new_solana_summit)
            db_solana_summit = new_solana_summit
            
        # Convert to Pydantic model
        response = SolanaSummitResponse.from_orm(db_solana_summit)
        
        # Store in cache if caching is enabled
        if use_cache:
            solana_summit_cache[cache_key] = response
            
        return response
        
    except SQLAlchemyError as e:
        error_msg = f"Database error in get_solana_summit: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

@router.put("/solana-summit", response_model=SolanaSummitResponse)
async def update_solana_summit(
    summit_data: SolanaSummitUpdate,
    db: Session = Depends(get_db)
):
    """
    Update the Solana Summit information.
    If none exists, creates a new entry.
    """
    try:
        # Try to get the first solana summit entry
        db_solana_summit = db.query(SolanaSummit).first()
        
        # If no entry exists, create a new one
        if not db_solana_summit:
            db_solana_summit = SolanaSummit(content=summit_data.content)
            db.add(db_solana_summit)
        else:
            # Update existing entry
            db_solana_summit.content = summit_data.content
            db_solana_summit.updated_at = datetime.utcnow()
            
        db.commit()
        db.refresh(db_solana_summit)
        
        # Clear cache
        if "solana_summit" in solana_summit_cache:
            del solana_summit_cache["solana_summit"]
        
        # Convert to Pydantic model
        return SolanaSummitResponse.from_orm(db_solana_summit)
        
    except SQLAlchemyError as e:
        error_msg = f"Database error in update_solana_summit: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg) 