import logging
import json
import traceback
from datetime import datetime, timedelta, timezone
import time
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body, Response
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
from app.database.models import FAQItem, EmergencyItem, EventItem, AboutPixity, SolanaSummit, DaNangBucketList, ApiKey, VectorDatabase, Document, VectorStatus, TelegramBot, ChatEngine, BotEngine, EngineVectorDb, DocumentContent
from pydantic import BaseModel, Field, ConfigDict

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
    
    model_config = ConfigDict(from_attributes=True)

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
    section: Optional[str] = None
    section_id: Optional[int] = None

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
    section: Optional[str] = None
    section_id: Optional[int] = None

class EmergencyResponse(EmergencyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
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
    
    model_config = ConfigDict(from_attributes=True)

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
        result = [FAQResponse.model_validate(faq, from_attributes=True) for faq in faqs]
        
        # Store in cache if caching is enabled
        if use_cache:
            faqs_cache[cache_key] = result
            
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
        db_faq = FAQItem(**faq.model_dump())
        db.add(db_faq)
        db.commit()
        db.refresh(db_faq)
        
        # Invalidate FAQ cache after creating a new item
        faqs_cache.clear()
        
        # Convert to Pydantic model
        return FAQResponse.model_validate(db_faq, from_attributes=True)
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
    Get a single FAQ item by ID.
    
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
        response = FAQResponse.model_validate(faq, from_attributes=True)
        
        # Store in cache if caching is enabled
        if use_cache:
            faqs_cache[cache_key] = response
            
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
    Update an existing FAQ item.
    
    - **faq_id**: ID of the FAQ item to update
    - **question**: Updated question text (optional)
    - **answer**: Updated answer text (optional)
    - **is_active**: Updated active status (optional)
    """
    try:
        # Check if FAQ exists
        faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
        if faq is None:
            raise HTTPException(status_code=404, detail=f"FAQ with ID {faq_id} not found")
        
        # Update fields with optimized dict handling
        update_data = faq_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(faq, key, value)
            
        # Commit changes
        db.commit()
        db.refresh(faq)
        
        # Invalidate specific cache entries
        faqs_cache.delete(f"faq_{faq_id}")
        faqs_cache.clear()  # Clear all list caches
        
        # Convert to Pydantic model
        return FAQResponse.model_validate(faq, from_attributes=True)
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
    Delete an FAQ item.
    
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

# --- Emergency contact endpoints ---

@router.get("/emergency", response_model=List[EmergencyResponse])
async def get_emergency_contacts(
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    section: Optional[str] = None,
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get all emergency contacts.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    - **section**: Filter by section (16.1, 16.2.1, 16.2.2, 16.3)
    - **use_cache**: If true, use cached results when available
    """
    try:
        # Generate cache key based on query parameters
        cache_key = f"emergency_{skip}_{limit}_{active_only}_{section}"
        
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
            
        if section:
            query = query.filter(EmergencyItem.section == section)
        
        # Get total count for pagination info
        count_query = query.with_entities(func.count(EmergencyItem.id))
        total_count = count_query.scalar()
        
        # Order by priority for proper sorting
        emergency_contacts = query.order_by(EmergencyItem.priority.desc()).offset(skip).limit(limit).all()
        
        # Convert to Pydantic models efficiently
        result = [EmergencyResponse.model_validate(contact, from_attributes=True) for contact in emergency_contacts]
        
        # Store in cache if caching is enabled
        if use_cache:
            emergencies_cache[cache_key] = result
            
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_emergency_contacts: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in get_emergency_contacts: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.get("/emergency/sections", response_model=List[Dict[str, Any]])
async def get_emergency_sections(
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get all available emergency sections.
    
    Returns a list of section information including ID and name.
    """
    try:
        # Generate cache key
        cache_key = "emergency_sections"
        
        # Try to get from cache if caching is enabled
        if use_cache:
            cached_result = emergencies_cache.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for {cache_key}")
                return cached_result
                
        # Query distinct sections with their IDs
        stmt = text("""
            SELECT DISTINCT section_id, section 
            FROM emergency_item 
            WHERE section IS NOT NULL 
            ORDER BY section_id
        """)
        result = db.execute(stmt)
        
        # Extract section info
        sections = [{"id": row[0], "name": row[1]} for row in result]
        
        # Store in cache if caching is enabled
        if use_cache:
            emergencies_cache[cache_key] = sections
            
        return sections
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_emergency_sections: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in get_emergency_sections: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.get("/emergency/section/{section_id}", response_model=List[EmergencyResponse])
async def get_emergency_contacts_by_section_id(
    section_id: int = Path(..., description="Section ID (1, 2, 3, or 4)"),
    active_only: bool = True,
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get emergency contacts for a specific section ID.
    
    - **section_id**: Section ID (1: Tourist support, 2: Emergency numbers, 3: Emergency situations, 4: Tourist scams)
    - **active_only**: If true, only return active items
    - **use_cache**: If true, use cached results when available
    """
    try:
        # Generate cache key based on query parameters
        cache_key = f"emergency_section_id_{section_id}_{active_only}"
        
        # Try to get from cache if caching is enabled
        if use_cache:
            cached_result = emergencies_cache.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for {cache_key}")
                return cached_result
                
        # Build query
        query = db.query(EmergencyItem).filter(EmergencyItem.section_id == section_id)
        
        # Add active filter if needed
        if active_only:
            query = query.filter(EmergencyItem.is_active == True)
        
        # Order by priority for proper sorting
        emergency_contacts = query.order_by(EmergencyItem.priority.desc()).all()
        
        # Convert to Pydantic models efficiently
        result = [EmergencyResponse.model_validate(contact, from_attributes=True) for contact in emergency_contacts]
        
        # Store in cache if caching is enabled
        if use_cache:
            emergencies_cache[cache_key] = result
            
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_emergency_contacts_by_section_id: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in get_emergency_contacts_by_section_id: {e}")
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
        db_emergency = EmergencyItem(**emergency.model_dump())
        db.add(db_emergency)
        db.commit()
        db.refresh(db_emergency)
        
        # Invalidate emergency cache after creating a new item
        emergencies_cache.clear()
        
        # Convert SQLAlchemy model to Pydantic model before returning
        result = EmergencyResponse.model_validate(db_emergency, from_attributes=True)
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
    Get a single emergency contact by ID.
    
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
        response = EmergencyResponse.model_validate(emergency, from_attributes=True)
        
        # Store in cache if caching is enabled
        if use_cache:
            emergencies_cache[cache_key] = response
            
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
        update_data = emergency_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(emergency, key, value)
            
        db.commit()
        db.refresh(emergency)
        
        # Invalidate specific cache entries
        emergencies_cache.delete(f"emergency_{emergency_id}")
        emergencies_cache.clear()  # Clear all list caches
        
        # Convert to Pydantic model
        return EmergencyResponse.model_validate(emergency, from_attributes=True)
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
        result = [EventResponse.model_validate(event, from_attributes=True) for event in events]
        
        # Store in cache if caching is enabled (30 seconds TTL for events list)
        if use_cache:
            events_cache[cache_key] = result
            
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
        db_event = EventItem(**event.model_dump())
        db.add(db_event)
        db.commit()
        db.refresh(db_event)
        
        # Invalidate relevant caches on create
        events_cache.clear()
        
        # Convert SQLAlchemy model to Pydantic model before returning
        result = EventResponse.model_validate(db_event, from_attributes=True)
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
    Get a single event by ID.
    
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
        response = EventResponse.model_validate(event, from_attributes=True)
        
        # Store in cache if caching is enabled (60 seconds TTL for single event)
        if use_cache:
            events_cache[cache_key] = response
            
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
        for key, value in event.model_dump(exclude_unset=True).items():
            setattr(db_event, key, value)
            
        db.commit()
        db.refresh(db_event)
        
        # Invalidate specific cache entries
        events_cache.delete(f"event_{event_id}")
        events_cache.clear()  # Clear all list caches
        
        # Convert SQLAlchemy model to Pydantic model before returning
        result = EventResponse.model_validate(db_event, from_attributes=True)
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
        if event is None:
            raise HTTPException(status_code=404, detail=f"Event with ID {event_id} not found")
        
        db.delete(event)
        db.commit()
        
        # Invalidate cache entries
        events_cache.delete(f"event_{event_id}")
        events_cache.clear()  # Clear all list caches
        
        return {"status": "success", "message": f"Event {event_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

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
            db_event = EventItem(**event_data.model_dump())
            db.add(db_event)
            db_events.append(db_event)
        
        # Commit all events in a single transaction
        db.commit()
        
        # Refresh all events to get their IDs and other generated fields
        for db_event in db_events:
            db.refresh(db_event)
        
        # Convert SQLAlchemy models to Pydantic models
        result = [EventResponse.model_validate(event, from_attributes=True) for event in db_events]
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
            db_faq = FAQItem(**faq_data.model_dump())
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
        result = [FAQResponse.model_validate(faq, from_attributes=True) for faq in db_faqs]
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
            db_emergency = EmergencyItem(**emergency_data.model_dump())
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
        result = [EmergencyResponse.model_validate(emergency, from_attributes=True) for emergency in db_emergency_contacts]
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
            about_pixity_cache["about_pixity"] = response
            
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
    
    model_config = ConfigDict(from_attributes=True)
        
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
        response = DaNangBucketListResponse.model_validate(db_bucket_list, from_attributes=True)
        
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
        return DaNangBucketListResponse.model_validate(db_bucket_list, from_attributes=True)
        
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
    
    model_config = ConfigDict(from_attributes=True)
        
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
        response = SolanaSummitResponse.model_validate(db_solana_summit, from_attributes=True)
        
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
        return SolanaSummitResponse.model_validate(db_solana_summit, from_attributes=True)
        
    except SQLAlchemyError as e:
        error_msg = f"Database error in update_solana_summit: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

# --- API Key models and endpoints ---
class ApiKeyBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class ApiKeyCreate(ApiKeyBase):
    pass

class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class ApiKeyResponse(ApiKeyBase):
    id: int
    key: str
    created_at: datetime
    last_used: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

@router.get("/api-keys", response_model=List[ApiKeyResponse])
async def get_api_keys(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get all API keys.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active keys
    """
    try:
        query = db.query(ApiKey)
        
        if active_only:
            query = query.filter(ApiKey.is_active == True)
        
        api_keys = query.offset(skip).limit(limit).all()
        return [ApiKeyResponse.model_validate(key, from_attributes=True) for key in api_keys]
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving API keys: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving API keys: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving API keys: {str(e)}")

@router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    api_key: ApiKeyCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new API key.
    """
    try:
        # Generate a secure API key
        import secrets
        import string
        import time
        
        # Create a random key with a prefix for easier identification
        prefix = "px_"
        random_key = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        timestamp = hex(int(time.time()))[2:]
        
        # Combine parts for the final key
        key_value = f"{prefix}{timestamp}_{random_key}"
        
        # Create API key object
        db_api_key = ApiKey(
            name=api_key.name,
            key=key_value,
            description=api_key.description,
            is_active=api_key.is_active
        )
        
        db.add(db_api_key)
        db.commit()
        db.refresh(db_api_key)
        
        return ApiKeyResponse.model_validate(db_api_key, from_attributes=True)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating API key: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating API key: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error creating API key: {str(e)}")

@router.get("/api-keys/{api_key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    api_key_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get API key by ID.
    """
    try:
        api_key = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
        if not api_key:
            raise HTTPException(status_code=404, detail=f"API key with ID {api_key_id} not found")
        
        return ApiKeyResponse.model_validate(api_key, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving API key: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving API key: {str(e)}")

@router.put("/api-keys/{api_key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    api_key_id: int = Path(..., gt=0),
    api_key_update: ApiKeyUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update API key details.
    """
    try:
        db_api_key = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
        if not db_api_key:
            raise HTTPException(status_code=404, detail=f"API key with ID {api_key_id} not found")
        
        # Update fields if provided
        if api_key_update.name is not None:
            db_api_key.name = api_key_update.name
        if api_key_update.description is not None:
            db_api_key.description = api_key_update.description
        if api_key_update.is_active is not None:
            db_api_key.is_active = api_key_update.is_active
        
        db.commit()
        db.refresh(db_api_key)
        
        return ApiKeyResponse.model_validate(db_api_key, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating API key: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating API key: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error updating API key: {str(e)}")

@router.delete("/api-keys/{api_key_id}", response_model=dict)
async def delete_api_key(
    api_key_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete API key.
    """
    try:
        db_api_key = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
        if not db_api_key:
            raise HTTPException(status_code=404, detail=f"API key with ID {api_key_id} not found")
        
        db.delete(db_api_key)
        db.commit()
        
        return {"message": f"API key with ID {api_key_id} deleted successfully"}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting API key: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting API key: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error deleting API key: {str(e)}")

@router.get("/api-keys/validate/{key}", response_model=dict)
async def validate_api_key(
    key: str,
    db: Session = Depends(get_db)
):
    """
    Validate an API key and update its last_used timestamp.
    """
    try:
        db_api_key = db.query(ApiKey).filter(ApiKey.key == key, ApiKey.is_active == True).first()
        if not db_api_key:
            return {"valid": False, "message": "Invalid or inactive API key"}
        
        # Update last_used timestamp
        db_api_key.last_used = datetime.utcnow()
        db.commit()
        
        return {
            "valid": True,
            "name": db_api_key.name,
            "id": db_api_key.id,
            "message": "API key is valid"
        }
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        logger.error(traceback.format_exc())
        return {"valid": False, "message": f"Error validating API key: {str(e)}"}

# --- Vector Database models and endpoints ---
class VectorDatabaseBase(BaseModel):
    name: str
    description: Optional[str] = None
    pinecone_index: str
    api_key_id: int  # Use API key ID instead of direct API key
    status: str = "active"

class VectorDatabaseCreate(VectorDatabaseBase):
    pass

class VectorDatabaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    pinecone_index: Optional[str] = None
    api_key_id: Optional[int] = None  # Updated to use API key ID
    status: Optional[str] = None

class VectorDatabaseResponse(VectorDatabaseBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class VectorDatabaseDetailResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    pinecone_index: str
    status: str
    created_at: datetime
    updated_at: datetime
    document_count: int
    embedded_count: int
    pending_count: int
    
    model_config = ConfigDict(from_attributes=True)

@router.get("/vector-databases", response_model=List[VectorDatabaseResponse])
async def get_vector_databases(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all vector databases.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **status**: Filter by status (e.g., 'active', 'inactive')
    """
    try:
        query = db.query(VectorDatabase)
        
        if status:
            query = query.filter(VectorDatabase.status == status)
        
        vector_dbs = query.offset(skip).limit(limit).all()
        return [VectorDatabaseResponse.model_validate(db_item, from_attributes=True) for db_item in vector_dbs]
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving vector databases: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving vector databases: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving vector databases: {str(e)}")

@router.post("/vector-databases", response_model=VectorDatabaseResponse)
async def create_vector_database(
    vector_db: VectorDatabaseCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new vector database.
    """
    try:
        # Check if a database with the same name already exists
        existing_db = db.query(VectorDatabase).filter(VectorDatabase.name == vector_db.name).first()
        if existing_db:
            raise HTTPException(status_code=400, detail=f"Vector database with name '{vector_db.name}' already exists")
        
        # Check if the API key exists
        api_key = db.query(ApiKey).filter(ApiKey.id == vector_db.api_key_id).first()
        if not api_key:
            raise HTTPException(status_code=400, detail=f"API key with ID {vector_db.api_key_id} not found")
        
        # Create new vector database
        db_vector_db = VectorDatabase(**vector_db.model_dump())
        
        db.add(db_vector_db)
        db.commit()
        db.refresh(db_vector_db)
        
        return VectorDatabaseResponse.model_validate(db_vector_db, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating vector database: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating vector database: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error creating vector database: {str(e)}")

@router.get("/vector-databases/{vector_db_id}", response_model=VectorDatabaseResponse)
async def get_vector_database(
    vector_db_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get vector database by ID.
    """
    try:
        vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == vector_db_id).first()
        if not vector_db:
            raise HTTPException(status_code=404, detail=f"Vector database with ID {vector_db_id} not found")
        
        return VectorDatabaseResponse.model_validate(vector_db, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving vector database: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving vector database: {str(e)}")

@router.put("/vector-databases/{vector_db_id}", response_model=VectorDatabaseResponse)
async def update_vector_database(
    vector_db_id: int = Path(..., gt=0),
    vector_db_update: VectorDatabaseUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update vector database details.
    """
    try:
        db_vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == vector_db_id).first()
        if not db_vector_db:
            raise HTTPException(status_code=404, detail=f"Vector database with ID {vector_db_id} not found")
        
        # Check name uniqueness if updating name
        if vector_db_update.name and vector_db_update.name != db_vector_db.name:
            existing_db = db.query(VectorDatabase).filter(VectorDatabase.name == vector_db_update.name).first()
            if existing_db:
                raise HTTPException(status_code=400, detail=f"Vector database with name '{vector_db_update.name}' already exists")
        
        # Check if API key exists if updating API key ID
        if vector_db_update.api_key_id:
            api_key = db.query(ApiKey).filter(ApiKey.id == vector_db_update.api_key_id).first()
            if not api_key:
                raise HTTPException(status_code=400, detail=f"API key with ID {vector_db_update.api_key_id} not found")
        
        # Update fields if provided
        update_data = vector_db_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(db_vector_db, key, value)
        
        db.commit()
        db.refresh(db_vector_db)
        
        return VectorDatabaseResponse.model_validate(db_vector_db, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating vector database: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating vector database: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error updating vector database: {str(e)}")

@router.delete("/vector-databases/{vector_db_id}", response_model=dict)
async def delete_vector_database(
    vector_db_id: int = Path(..., gt=0),
    force: bool = Query(False, description="Force deletion even if documents exist"),
    db: Session = Depends(get_db)
):
    """
    Delete vector database.
    
    - **force**: If true, will delete all associated documents first
    """
    try:
        db_vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == vector_db_id).first()
        if not db_vector_db:
            raise HTTPException(status_code=404, detail=f"Vector database with ID {vector_db_id} not found")
        
        # Check if there are documents associated with this database
        doc_count = db.query(func.count(Document.id)).filter(Document.vector_database_id == vector_db_id).scalar()
        if doc_count > 0 and not force:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot delete vector database with {doc_count} documents. Use force=true to delete anyway."
            )
        
        # If force=true, delete all associated documents first
        if force and doc_count > 0:
            # Delete all documents associated with this database
            db.query(Document).filter(Document.vector_database_id == vector_db_id).delete()
            
            # Delete all vector statuses associated with this database
            db.query(VectorStatus).filter(VectorStatus.vector_database_id == vector_db_id).delete()
            
            # Delete all engine-vector-db associations
            db.query(EngineVectorDb).filter(EngineVectorDb.vector_database_id == vector_db_id).delete()
        
        # Delete the vector database
        db.delete(db_vector_db)
        db.commit()
        
        return {"message": f"Vector database with ID {vector_db_id} deleted successfully"}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting vector database: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting vector database: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error deleting vector database: {str(e)}")

@router.get("/vector-databases/{vector_db_id}/info", response_model=VectorDatabaseDetailResponse)
async def get_vector_database_info(
    vector_db_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a vector database including document counts.
    """
    try:
        # Get the vector database
        vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == vector_db_id).first()
        if not vector_db:
            raise HTTPException(status_code=404, detail="Vector database not found")
        
        # Count total documents
        total_docs = db.query(func.count(Document.id)).filter(
            Document.vector_database_id == vector_db_id
        ).scalar()
        
        # Count embedded documents
        embedded_docs = db.query(func.count(Document.id)).filter(
            Document.vector_database_id == vector_db_id,
            Document.is_embedded == True
        ).scalar()
        
        # Count pending documents (not embedded)
        pending_docs = db.query(func.count(Document.id)).filter(
            Document.vector_database_id == vector_db_id,
            Document.is_embedded == False
        ).scalar()
        
        # Create response with added counts
        result = VectorDatabaseDetailResponse(
            id=vector_db.id,
            name=vector_db.name,
            description=vector_db.description,
            pinecone_index=vector_db.pinecone_index,
            status=vector_db.status,
            created_at=vector_db.created_at,
            updated_at=vector_db.updated_at,
            document_count=total_docs or 0,
            embedded_count=embedded_docs or 0,
            pending_count=pending_docs or 0
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting vector database info: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting vector database info: {str(e)}")

# --- Document models and endpoints ---
class DocumentBase(BaseModel):
    name: str
    vector_database_id: int

class DocumentCreate(BaseModel):
    name: str
    vector_database_id: int

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

@router.get("/documents", response_model=List[DocumentResponse])
async def get_documents(
    skip: int = 0,
    limit: int = 100,
    vector_database_id: Optional[int] = None,
    is_embedded: Optional[bool] = None,
    file_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all documents with optional filtering.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **vector_database_id**: Filter by vector database ID
    - **is_embedded**: Filter by embedding status
    - **file_type**: Filter by file type
    """
    try:
        query = db.query(Document)
        
        # Apply filters if provided
        if vector_database_id is not None:
            query = query.filter(Document.vector_database_id == vector_database_id)
        
        if is_embedded is not None:
            query = query.filter(Document.is_embedded == is_embedded)
            
        if file_type is not None:
            query = query.filter(Document.file_type == file_type)
        
        # Execute query with pagination
        documents = query.offset(skip).limit(limit).all()
        
        # Add vector database name
        result = []
        for doc in documents:
            doc_dict = DocumentResponse.model_validate(doc, from_attributes=True)
            
            # Get vector database name if not already populated
            if not hasattr(doc, 'vector_database_name') or doc.vector_database_name is None:
                vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == doc.vector_database_id).first()
                vector_db_name = vector_db.name if vector_db else f"db_{doc.vector_database_id}"
                doc_dict.vector_database_name = vector_db_name
                
            result.append(doc_dict)
        
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving documents: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving documents: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving documents: {str(e)}")

@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get document by ID.
    """
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"Document with ID {document_id} not found")
        
        # Get vector database name
        vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == document.vector_database_id).first()
        vector_db_name = vector_db.name if vector_db else f"db_{document.vector_database_id}"
        
        # Create response with vector database name
        result = DocumentResponse.model_validate(document, from_attributes=True)
        result.vector_database_name = vector_db_name
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving document: {str(e)}")

@router.get("/documents/{document_id}/content", response_class=Response)
async def get_document_content(
    document_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get document content (file) by document ID.
    Returns the binary content with the appropriate Content-Type header.
    """
    try:
        # Get document to check if it exists and get metadata
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"Document with ID {document_id} not found")
        
        # Get document content from document_content table
        document_content = db.query(DocumentContent).filter(DocumentContent.document_id == document_id).first()
        if not document_content or not document_content.file_content:
            raise HTTPException(status_code=404, detail=f"Content for document with ID {document_id} not found")
        
        # Determine content type
        content_type = document.content_type if hasattr(document, 'content_type') and document.content_type else "application/octet-stream"
        
        # Return binary content with correct content type
        return Response(
            content=document_content.file_content,
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename=\"{document.name}\""}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document content: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving document content: {str(e)}")

# --- Telegram Bot models and endpoints ---
class TelegramBotBase(BaseModel):
    name: str
    username: str
    token: str
    status: str = "inactive"

class TelegramBotCreate(TelegramBotBase):
    pass

class TelegramBotUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    token: Optional[str] = None
    status: Optional[str] = None

class TelegramBotResponse(TelegramBotBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

@router.get("/telegram-bots/{bot_id}", response_model=TelegramBotResponse)
async def get_telegram_bot(
    bot_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get Telegram bot by ID.
    """
    try:
        bot = db.query(TelegramBot).filter(TelegramBot.id == bot_id).first()
        if not bot:
            raise HTTPException(status_code=404, detail=f"Telegram bot with ID {bot_id} not found")
        
        return TelegramBotResponse.model_validate(bot, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving Telegram bot: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving Telegram bot: {str(e)}")

@router.put("/telegram-bots/{bot_id}", response_model=TelegramBotResponse)
async def update_telegram_bot(
    bot_id: int = Path(..., gt=0),
    bot_update: TelegramBotUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update Telegram bot details.
    """
    try:
        db_bot = db.query(TelegramBot).filter(TelegramBot.id == bot_id).first()
        if not db_bot:
            raise HTTPException(status_code=404, detail=f"Telegram bot with ID {bot_id} not found")
        
        # Check if new username conflicts with existing bots
        if bot_update.username and bot_update.username != db_bot.username:
            existing_bot = db.query(TelegramBot).filter(TelegramBot.username == bot_update.username).first()
            if existing_bot:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Telegram bot with username '{bot_update.username}' already exists"
                )
        
        # Update fields if provided
        update_data = bot_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(db_bot, key, value)
        
        db.commit()
        db.refresh(db_bot)
        
        return TelegramBotResponse.model_validate(db_bot, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating Telegram bot: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating Telegram bot: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error updating Telegram bot: {str(e)}")

@router.delete("/telegram-bots/{bot_id}", response_model=dict)
async def delete_telegram_bot(
    bot_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete Telegram bot.
    """
    try:
        db_bot = db.query(TelegramBot).filter(TelegramBot.id == bot_id).first()
        if not db_bot:
            raise HTTPException(status_code=404, detail=f"Telegram bot with ID {bot_id} not found")
        
        # Check if bot is associated with any engines
        bot_engines = db.query(BotEngine).filter(BotEngine.bot_id == bot_id).all()
        if bot_engines:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete bot as it is associated with chat engines. Remove associations first."
            )
        
        # Delete bot
        db.delete(db_bot)
        db.commit()
        
        return {"message": f"Telegram bot with ID {bot_id} deleted successfully"}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting Telegram bot: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting Telegram bot: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error deleting Telegram bot: {str(e)}")

@router.get("/telegram-bots/{bot_id}/engines", response_model=List[dict])
async def get_bot_engines_info(
    bot_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get all chat engines associated with a Telegram bot.
    """
    try:
        # Verify bot exists
        bot = db.query(TelegramBot).filter(TelegramBot.id == bot_id).first()
        if not bot:
            raise HTTPException(status_code=404, detail=f"Telegram bot with ID {bot_id} not found")
        
        # Get associated engines through BotEngine
        bot_engines = db.query(BotEngine).filter(BotEngine.bot_id == bot_id).all()
        
        result = []
        for association in bot_engines:
            engine = db.query(ChatEngine).filter(ChatEngine.id == association.engine_id).first()
            if engine:
                result.append({
                    "association_id": association.id,
                    "engine_id": engine.id,
                    "engine_name": engine.name,
                    "answer_model": engine.answer_model,
                    "status": engine.status,
                    "created_at": association.created_at
                })
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving bot engines: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving bot engines: {str(e)}") 

# --- Chat Engine models and endpoints ---
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

class ChatEngineUpdate(BaseModel):
    name: Optional[str] = None
    answer_model: Optional[str] = None
    system_prompt: Optional[str] = None
    empty_response: Optional[str] = None
    similarity_top_k: Optional[int] = None
    vector_distance_threshold: Optional[float] = None
    grounding_threshold: Optional[float] = None
    use_public_information: Optional[bool] = None
    status: Optional[str] = None

class ChatEngineResponse(ChatEngineBase):
    id: int
    created_at: datetime
    last_modified: datetime
    
    model_config = ConfigDict(from_attributes=True)

@router.get("/chat-engines", response_model=List[ChatEngineResponse])
async def get_chat_engines(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all chat engines.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **status**: Filter by status (e.g., 'active', 'inactive')
    """
    try:
        query = db.query(ChatEngine)
        
        if status:
            query = query.filter(ChatEngine.status == status)
        
        engines = query.offset(skip).limit(limit).all()
        return [ChatEngineResponse.model_validate(engine, from_attributes=True) for engine in engines]
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving chat engines: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving chat engines: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving chat engines: {str(e)}")

@router.post("/chat-engines", response_model=ChatEngineResponse)
async def create_chat_engine(
    engine: ChatEngineCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new chat engine.
    """
    try:
        # Create chat engine
        db_engine = ChatEngine(**engine.model_dump())
        
        db.add(db_engine)
        db.commit()
        db.refresh(db_engine)
        
        return ChatEngineResponse.model_validate(db_engine, from_attributes=True)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating chat engine: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating chat engine: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error creating chat engine: {str(e)}")

@router.get("/chat-engines/{engine_id}", response_model=ChatEngineResponse)
async def get_chat_engine(
    engine_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get chat engine by ID.
    """
    try:
        engine = db.query(ChatEngine).filter(ChatEngine.id == engine_id).first()
        if not engine:
            raise HTTPException(status_code=404, detail=f"Chat engine with ID {engine_id} not found")
        
        return ChatEngineResponse.model_validate(engine, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving chat engine: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving chat engine: {str(e)}")

@router.put("/chat-engines/{engine_id}", response_model=ChatEngineResponse)
async def update_chat_engine(
    engine_id: int = Path(..., gt=0),
    engine_update: ChatEngineUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update chat engine details.
    """
    try:
        db_engine = db.query(ChatEngine).filter(ChatEngine.id == engine_id).first()
        if not db_engine:
            raise HTTPException(status_code=404, detail=f"Chat engine with ID {engine_id} not found")
        
        # Update fields if provided
        update_data = engine_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(db_engine, key, value)
        
        # Update last_modified timestamp
        db_engine.last_modified = datetime.utcnow()
        
        db.commit()
        db.refresh(db_engine)
        
        return ChatEngineResponse.model_validate(db_engine, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating chat engine: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating chat engine: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error updating chat engine: {str(e)}")

@router.delete("/chat-engines/{engine_id}", response_model=dict)
async def delete_chat_engine(
    engine_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete chat engine.
    """
    try:
        db_engine = db.query(ChatEngine).filter(ChatEngine.id == engine_id).first()
        if not db_engine:
            raise HTTPException(status_code=404, detail=f"Chat engine with ID {engine_id} not found")
        
        # Check if engine has associated bots or vector databases
        bot_engine_count = db.query(func.count(BotEngine.id)).filter(BotEngine.engine_id == engine_id).scalar()
        vector_db_count = db.query(func.count(EngineVectorDb.id)).filter(EngineVectorDb.engine_id == engine_id).scalar()
        
        if bot_engine_count > 0 or vector_db_count > 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete chat engine as it has associated bots or vector databases. Remove associations first."
            )
        
        # Delete engine
        db.delete(db_engine)
        db.commit()
        
        return {"message": f"Chat engine with ID {engine_id} deleted successfully"}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting chat engine: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting chat engine: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error deleting chat engine: {str(e)}")

@router.get("/chat-engines/{engine_id}/vector-databases", response_model=List[dict])
async def get_engine_vector_databases(
    engine_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get all vector databases associated with a chat engine.
    """
    try:
        # Verify engine exists
        engine = db.query(ChatEngine).filter(ChatEngine.id == engine_id).first()
        if not engine:
            raise HTTPException(status_code=404, detail=f"Chat engine with ID {engine_id} not found")
        
        # Get associated vector databases through EngineVectorDb
        engine_vector_dbs = db.query(EngineVectorDb).filter(EngineVectorDb.engine_id == engine_id).all()
        
        result = []
        for association in engine_vector_dbs:
            vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == association.vector_database_id).first()
            if vector_db:
                result.append({
                    "association_id": association.id,
                    "vector_database_id": vector_db.id,
                    "name": vector_db.name,
                    "pinecone_index": vector_db.pinecone_index,
                    "priority": association.priority,
                    "status": vector_db.status
                })
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving engine vector databases: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving engine vector databases: {str(e)}")

# --- Bot Engine Association models and endpoints ---
class BotEngineCreate(BaseModel):
    bot_id: int
    engine_id: int

class BotEngineResponse(BotEngineCreate):
    id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

@router.get("/bot-engines", response_model=List[BotEngineResponse])
async def get_bot_engines(
    skip: int = 0,
    limit: int = 100,
    bot_id: Optional[int] = None,
    engine_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get all bot-engine associations.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **bot_id**: Filter by bot ID
    - **engine_id**: Filter by engine ID
    """
    try:
        query = db.query(BotEngine)
        
        if bot_id is not None:
            query = query.filter(BotEngine.bot_id == bot_id)
            
        if engine_id is not None:
            query = query.filter(BotEngine.engine_id == engine_id)
        
        bot_engines = query.offset(skip).limit(limit).all()
        return [BotEngineResponse.model_validate(association, from_attributes=True) for association in bot_engines]
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving bot-engine associations: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving bot-engine associations: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving bot-engine associations: {str(e)}")

@router.post("/bot-engines", response_model=BotEngineResponse)
async def create_bot_engine(
    bot_engine: BotEngineCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new bot-engine association.
    """
    try:
        # Check if bot exists
        bot = db.query(TelegramBot).filter(TelegramBot.id == bot_engine.bot_id).first()
        if not bot:
            raise HTTPException(status_code=404, detail=f"Telegram bot with ID {bot_engine.bot_id} not found")
        
        # Check if engine exists
        engine = db.query(ChatEngine).filter(ChatEngine.id == bot_engine.engine_id).first()
        if not engine:
            raise HTTPException(status_code=404, detail=f"Chat engine with ID {bot_engine.engine_id} not found")
        
        # Check if association already exists
        existing_association = db.query(BotEngine).filter(
            BotEngine.bot_id == bot_engine.bot_id,
            BotEngine.engine_id == bot_engine.engine_id
        ).first()
        
        if existing_association:
            raise HTTPException(
                status_code=400,
                detail=f"Association between bot ID {bot_engine.bot_id} and engine ID {bot_engine.engine_id} already exists"
            )
        
        # Create association
        db_bot_engine = BotEngine(**bot_engine.model_dump())
        
        db.add(db_bot_engine)
        db.commit()
        db.refresh(db_bot_engine)
        
        return BotEngineResponse.model_validate(db_bot_engine, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating bot-engine association: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating bot-engine association: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error creating bot-engine association: {str(e)}")

@router.get("/bot-engines/{association_id}", response_model=BotEngineResponse)
async def get_bot_engine(
    association_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get bot-engine association by ID.
    """
    try:
        association = db.query(BotEngine).filter(BotEngine.id == association_id).first()
        if not association:
            raise HTTPException(status_code=404, detail=f"Bot-engine association with ID {association_id} not found")
        
        return BotEngineResponse.model_validate(association, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving bot-engine association: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving bot-engine association: {str(e)}")

@router.delete("/bot-engines/{association_id}", response_model=dict)
async def delete_bot_engine(
    association_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete bot-engine association.
    """
    try:
        association = db.query(BotEngine).filter(BotEngine.id == association_id).first()
        if not association:
            raise HTTPException(status_code=404, detail=f"Bot-engine association with ID {association_id} not found")
        
        db.delete(association)
        db.commit()
        
        return {"message": f"Bot-engine association with ID {association_id} deleted successfully"}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting bot-engine association: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting bot-engine association: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error deleting bot-engine association: {str(e)}")

# --- Engine-Vector DB Association models and endpoints ---
class EngineVectorDbCreate(BaseModel):
    engine_id: int
    vector_database_id: int
    priority: int = 0

class EngineVectorDbResponse(EngineVectorDbCreate):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

@router.get("/engine-vector-dbs", response_model=List[EngineVectorDbResponse])
async def get_engine_vector_dbs(
    skip: int = 0,
    limit: int = 100,
    engine_id: Optional[int] = None,
    vector_database_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get all engine-vector-db associations.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **engine_id**: Filter by engine ID
    - **vector_database_id**: Filter by vector database ID
    """
    try:
        query = db.query(EngineVectorDb)
        
        if engine_id is not None:
            query = query.filter(EngineVectorDb.engine_id == engine_id)
            
        if vector_database_id is not None:
            query = query.filter(EngineVectorDb.vector_database_id == vector_database_id)
        
        associations = query.offset(skip).limit(limit).all()
        return [EngineVectorDbResponse.model_validate(association, from_attributes=True) for association in associations]
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving engine-vector-db associations: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving engine-vector-db associations: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving engine-vector-db associations: {str(e)}")

@router.post("/engine-vector-dbs", response_model=EngineVectorDbResponse)
async def create_engine_vector_db(
    engine_vector_db: EngineVectorDbCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new engine-vector-db association.
    """
    try:
        # Check if engine exists
        engine = db.query(ChatEngine).filter(ChatEngine.id == engine_vector_db.engine_id).first()
        if not engine:
            raise HTTPException(status_code=404, detail=f"Chat engine with ID {engine_vector_db.engine_id} not found")
        
        # Check if vector database exists
        vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == engine_vector_db.vector_database_id).first()
        if not vector_db:
            raise HTTPException(status_code=404, detail=f"Vector database with ID {engine_vector_db.vector_database_id} not found")
        
        # Check if association already exists
        existing_association = db.query(EngineVectorDb).filter(
            EngineVectorDb.engine_id == engine_vector_db.engine_id,
            EngineVectorDb.vector_database_id == engine_vector_db.vector_database_id
        ).first()
        
        if existing_association:
            raise HTTPException(
                status_code=400,
                detail=f"Association between engine ID {engine_vector_db.engine_id} and vector database ID {engine_vector_db.vector_database_id} already exists"
            )
        
        # Create association
        db_engine_vector_db = EngineVectorDb(**engine_vector_db.model_dump())
        
        db.add(db_engine_vector_db)
        db.commit()
        db.refresh(db_engine_vector_db)
        
        return EngineVectorDbResponse.model_validate(db_engine_vector_db, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating engine-vector-db association: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating engine-vector-db association: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error creating engine-vector-db association: {str(e)}")

@router.get("/engine-vector-dbs/{association_id}", response_model=EngineVectorDbResponse)
async def get_engine_vector_db(
    association_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get engine-vector-db association by ID.
    """
    try:
        association = db.query(EngineVectorDb).filter(EngineVectorDb.id == association_id).first()
        if not association:
            raise HTTPException(status_code=404, detail=f"Engine-vector-db association with ID {association_id} not found")
        
        return EngineVectorDbResponse.model_validate(association, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving engine-vector-db association: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving engine-vector-db association: {str(e)}")

@router.put("/engine-vector-dbs/{association_id}", response_model=EngineVectorDbResponse)
async def update_engine_vector_db(
    association_id: int = Path(..., gt=0),
    update_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update engine-vector-db association details (only priority can be updated).
    """
    try:
        association = db.query(EngineVectorDb).filter(EngineVectorDb.id == association_id).first()
        if not association:
            raise HTTPException(status_code=404, detail=f"Engine-vector-db association with ID {association_id} not found")
        
        # Only priority can be updated
        if "priority" in update_data:
            association.priority = update_data["priority"]
        
        db.commit()
        db.refresh(association)
        
        return EngineVectorDbResponse.model_validate(association, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating engine-vector-db association: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating engine-vector-db association: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error updating engine-vector-db association: {str(e)}")

@router.delete("/engine-vector-dbs/{association_id}", response_model=dict)
async def delete_engine_vector_db(
    association_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete engine-vector-db association.
    """
    try:
        association = db.query(EngineVectorDb).filter(EngineVectorDb.id == association_id).first()
        if not association:
            raise HTTPException(status_code=404, detail=f"Engine-vector-db association with ID {association_id} not found")
        
        db.delete(association)
        db.commit()
        
        return {"message": f"Engine-vector-db association with ID {association_id} deleted successfully"}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting engine-vector-db association: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting engine-vector-db association: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error deleting engine-vector-db association: {str(e)}")

# --- VectorStatus models and endpoints ---
class VectorStatusBase(BaseModel):
    document_id: int
    vector_database_id: int
    vector_id: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None

class VectorStatusCreate(VectorStatusBase):
    pass

class VectorStatusResponse(VectorStatusBase):
    id: int
    embedded_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

@router.get("/vector-statuses", response_model=List[VectorStatusResponse])
async def get_vector_statuses(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    document_id: Optional[int] = None,
    vector_database_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get all vector statuses with optional filtering.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **status**: Filter by status (e.g., 'pending', 'completed', 'error')
    - **document_id**: Filter by document ID
    - **vector_database_id**: Filter by vector database ID
    """
    try:
        query = db.query(VectorStatus)
        
        # Apply filters if provided
        if status is not None:
            query = query.filter(VectorStatus.status == status)
            
        if document_id is not None:
            query = query.filter(VectorStatus.document_id == document_id)
            
        if vector_database_id is not None:
            query = query.filter(VectorStatus.vector_database_id == vector_database_id)
        
        # Execute query with pagination
        vector_statuses = query.offset(skip).limit(limit).all()
        
        # Convert to Pydantic models
        return [VectorStatusResponse.model_validate(status, from_attributes=True) for status in vector_statuses]
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_vector_statuses: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving vector statuses: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving vector statuses: {str(e)}")

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
        db_emergency = EmergencyItem(**emergency.model_dump())
        db.add(db_emergency)
        db.commit()
        db.refresh(db_emergency)
        
        # Invalidate emergency cache after creating a new item
        emergencies_cache.clear()
        
        # Convert SQLAlchemy model to Pydantic model before returning
        result = EmergencyResponse.model_validate(db_emergency, from_attributes=True)
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
    Get a single emergency contact by ID.
    
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
        response = EmergencyResponse.model_validate(emergency, from_attributes=True)
        
        # Store in cache if caching is enabled
        if use_cache:
            emergencies_cache[cache_key] = response
            
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
        update_data = emergency_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(emergency, key, value)
            
        db.commit()
        db.refresh(emergency)
        
        # Invalidate specific cache entries
        emergencies_cache.delete(f"emergency_{emergency_id}")
        emergencies_cache.clear()  # Clear all list caches
        
        # Convert to Pydantic model
        return EmergencyResponse.model_validate(emergency, from_attributes=True)
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