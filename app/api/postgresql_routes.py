from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
import logging
from datetime import datetime

from app.database.postgresql import get_db
from app.database.models import FAQItem, EmergencyItem, EventItem
from pydantic import BaseModel, Field, ConfigDict

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
        query = db.query(FAQItem)
        if active_only:
            query = query.filter(FAQItem.is_active == True)
        faqs = query.offset(skip).limit(limit).all()
        return faqs
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

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
        # Sử dụng model_dump thay vì dict method
        db_faq = FAQItem(**faq.model_dump())
        db.add(db_faq)
        db.commit()
        db.refresh(db_faq)
        return db_faq
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
    Get a specific FAQ item by ID.
    
    - **faq_id**: ID of the FAQ item
    """
    try:
        faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ item not found")
        return faq
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

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
        faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ item not found")
        
        # Update fields if provided - sử dụng model_dump thay vì dict
        update_data = faq_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(faq, key, value)
            
        db.commit()
        db.refresh(faq)
        return faq
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update FAQ item")

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
        faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ item not found")
        
        db.delete(faq)
        db.commit()
        return {"status": "success", "message": f"FAQ item {faq_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete FAQ item")

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
        query = db.query(EmergencyItem)
        if active_only:
            query = query.filter(EmergencyItem.is_active == True)
        emergency_contacts = query.offset(skip).limit(limit).all()
        return emergency_contacts
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

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
        return db_emergency
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create emergency contact")

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
        emergency = db.query(EmergencyItem).filter(EmergencyItem.id == emergency_id).first()
        if not emergency:
            raise HTTPException(status_code=404, detail="Emergency contact not found")
        return emergency
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

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
        return emergency
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update emergency contact")

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
        emergency = db.query(EmergencyItem).filter(EmergencyItem.id == emergency_id).first()
        if not emergency:
            raise HTTPException(status_code=404, detail="Emergency contact not found")
        
        db.delete(emergency)
        db.commit()
        return {"status": "success", "message": f"Emergency contact {emergency_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete emergency contact")

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
        query = db.query(EventItem)
        if active_only:
            query = query.filter(EventItem.is_active == True)
        if featured_only:
            query = query.filter(EventItem.featured == True)
        events = query.offset(skip).limit(limit).all()
        return events
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

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
        return db_event
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create event")

@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Get a specific event by ID.
    
    - **event_id**: ID of the event
    """
    try:
        event = db.query(EventItem).filter(EventItem.id == event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return event
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@router.put("/events/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: int = Path(..., gt=0),
    event_update: EventUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update a specific event.
    
    - **event_id**: ID of the event to update
    - **name**: New name (optional)
    - **description**: New description (optional)
    - **address**: New address (optional)
    - **location**: New location coordinates (optional)
    - **date_start**: New start date and time (optional)
    - **date_end**: New end date and time (optional)
    - **price**: New price information (optional JSON object)
    - **is_active**: New active status (optional)
    - **featured**: New featured status (optional)
    """
    try:
        event = db.query(EventItem).filter(EventItem.id == event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Update fields if provided
        update_data = event_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(event, key, value)
            
        db.commit()
        db.refresh(event)
        return event
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update event")

@router.delete("/events/{event_id}", response_model=dict)
async def delete_event(
    event_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete a specific event.
    
    - **event_id**: ID of the event to delete
    """
    try:
        event = db.query(EventItem).filter(EventItem.id == event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        db.delete(event)
        db.commit()
        return {"status": "success", "message": f"Event {event_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete event")

# Health check endpoint
@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Check health of PostgreSQL connection.
    """
    try:
        # Perform a simple database query to check health
        db.execute("SELECT 1").first()
        return {"status": "healthy", "message": "PostgreSQL connection is working", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"PostgreSQL connection failed: {str(e)}") 