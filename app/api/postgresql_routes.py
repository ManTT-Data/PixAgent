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

from app.database.postgresql import get_db
from app.database.models import FAQItem, EmergencyItem, EventItem
from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/postgres",
    tags=["PostgreSQL"],
)

# Simple memory cache implementation
class Cache:
    """Simple in-memory cache with expiration"""
    def __init__(self):
        self._cache = {}
    
    def get(self, key, default=None):
        """Get a value from the cache if it exists and is not expired"""
        if key in self._cache:
            expiry, value = self._cache[key]
            if expiry > time.time():
                return value
            # Remove expired item
            del self._cache[key]
        return default
    
    def set(self, key, value, ttl_seconds=60):
        """Set a value in the cache with expiry time"""
        expiry = time.time() + ttl_seconds
        self._cache[key] = (expiry, value)
        return value
    
    def delete(self, key):
        """Delete a key from the cache"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """Clear the entire cache"""
        self._cache.clear()

# Create cache instances for different entity types
event_cache = Cache()
faq_cache = Cache()
emergency_cache = Cache()

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
    db: Session = Depends(get_db)
):
    """
    Get all FAQ items.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    """
    try:
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
    db: Session = Depends(get_db)
):
    """
    Get a specific FAQ item by ID.
    
    - **faq_id**: ID of the FAQ item
    """
    try:
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
        return FAQResponse.from_orm(faq)
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
    db: Session = Depends(get_db)
):
    """
    Get all emergency contacts.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    """
    try:
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
    db: Session = Depends(get_db)
):
    """
    Get a specific emergency contact by ID.
    
    - **emergency_id**: ID of the emergency contact
    """
    try:
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
        return EmergencyResponse.from_orm(emergency)
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
            cached_result = event_cache.get(cache_key)
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
            event_cache.set(cache_key, result, ttl_seconds=30)
            
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
        event_cache.clear()
        
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
            cached_result = event_cache.get(cache_key)
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
            event_cache.set(cache_key, response, ttl_seconds=60)
            
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
        event_cache.delete(f"event_{event_id}")
        event_cache.clear()  # Clear all list caches
        
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
        event_cache.delete(f"event_{event_id}")
        event_cache.clear()  # Clear all list caches
        
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