from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any
import logging
import traceback
from datetime import datetime
from sqlalchemy import text, inspect

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

# --- Diagnostic endpoints ---

@router.get("/debug/tables", response_model=Dict[str, Any])
async def debug_tables(db: Session = Depends(get_db)):
    """
    Get diagnostic information about database tables.
    """
    try:
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        
        result = {
            "status": "success",
            "tables": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # Get details for each table
        for table_name in tables:
            columns = inspector.get_columns(table_name)
            column_info = {col["name"]: {"type": str(col["type"]), "nullable": col["nullable"]} for col in columns}
            
            # Try to get row count
            try:
                count = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                
                # Get sample row if available
                sample = None
                if count > 0:
                    sample_row = db.execute(text(f"SELECT * FROM {table_name} LIMIT 1")).fetchone()
                    if sample_row:
                        sample = dict(zip([col["name"] for col in columns], sample_row))
                
                result["tables"][table_name] = {
                    "columns": column_info,
                    "row_count": count,
                    "sample": sample
                }
            except Exception as e:
                result["tables"][table_name] = {
                    "columns": column_info,
                    "error": str(e)
                }
        
        return result
    except Exception as e:
        logger.error(f"Error in debug_tables: {e}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat()
        }

@router.get("/debug/test-data", response_model=Dict[str, Any])
async def debug_test_data(db: Session = Depends(get_db)):
    """
    Test retrieving a single row from each important table using direct SQL queries.
    """
    try:
        result = {
            "status": "success",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # Test FAQ table
        try:
            faq_query = text("SELECT * FROM faq_item LIMIT 1")
            faq_row = db.execute(faq_query).fetchone()
            if faq_row:
                faq_columns = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'faq_item'")).fetchall()
                faq_column_names = [col[0] for col in faq_columns]
                result["data"]["faq_item"] = {"status": "success", "row": dict(zip(faq_column_names, faq_row))}
            else:
                result["data"]["faq_item"] = {"status": "empty", "message": "No rows found in faq_item"}
        except Exception as e:
            result["data"]["faq_item"] = {"status": "error", "error": str(e)}
        
        # Test emergency table
        try:
            emergency_query = text("SELECT * FROM emergency_item LIMIT 1")
            emergency_row = db.execute(emergency_query).fetchone()
            if emergency_row:
                emergency_columns = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'emergency_item'")).fetchall()
                emergency_column_names = [col[0] for col in emergency_columns]
                result["data"]["emergency_item"] = {"status": "success", "row": dict(zip(emergency_column_names, emergency_row))}
            else:
                result["data"]["emergency_item"] = {"status": "empty", "message": "No rows found in emergency_item"}
        except Exception as e:
            result["data"]["emergency_item"] = {"status": "error", "error": str(e)}
        
        # Test event table
        try:
            event_query = text("SELECT * FROM event_item LIMIT 1")
            event_row = db.execute(event_query).fetchone()
            if event_row:
                event_columns = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'event_item'")).fetchall()
                event_column_names = [col[0] for col in event_columns]
                result["data"]["event_item"] = {"status": "success", "row": dict(zip(event_column_names, event_row))}
            else:
                result["data"]["event_item"] = {"status": "empty", "message": "No rows found in event_item"}
        except Exception as e:
            result["data"]["event_item"] = {"status": "error", "error": str(e)}
        
        return result
    except Exception as e:
        logger.error(f"Error in debug_test_data: {e}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat()
        }

@router.get("/debug/test-models", response_model=Dict[str, Any])
async def debug_test_models():
    """
    Test creating model objects without database interaction to check serialization.
    """
    try:
        result = {
            "status": "success",
            "models": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # Test FAQ model
        try:
            # Create a test FAQ item
            faq_model = FAQItem(
                id=1,
                question="Test question?",
                answer="Test answer.",
                is_active=True,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # Convert to dict 
            faq_dict = {c.name: getattr(faq_model, c.name) for c in faq_model.__table__.columns}
            result["models"]["FAQItem"] = {"status": "success", "item": faq_dict}
        except Exception as e:
            result["models"]["FAQItem"] = {"status": "error", "error": str(e)}
        
        # Test Emergency model
        try:
            # Create a test Emergency item
            emergency_model = EmergencyItem(
                id=1,
                name="Test Emergency",
                phone_number="123-456-7890",
                description="Test description",
                address="Test address",
                location=None,
                priority=0,
                is_active=True,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # Convert to dict
            emergency_dict = {c.name: getattr(emergency_model, c.name) for c in emergency_model.__table__.columns}
            result["models"]["EmergencyItem"] = {"status": "success", "item": emergency_dict}
        except Exception as e:
            result["models"]["EmergencyItem"] = {"status": "error", "error": str(e)}
        
        # Test Event model
        try:
            # Create a test Event item
            event_model = EventItem(
                id=1,
                name="Test Event",
                description="Test description",
                address="Test address",
                location=None,
                date_start=datetime.now(),
                date_end=datetime.now(),
                price=[{"type": "standard", "amount": 10, "currency": "USD"}],
                is_active=True,
                featured=False,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # Convert to dict
            event_dict = {c.name: getattr(event_model, c.name) for c in event_model.__table__.columns}
            result["models"]["EventItem"] = {"status": "success", "item": event_dict}
        except Exception as e:
            result["models"]["EventItem"] = {"status": "error", "error": str(e)}
        
        return result
    except Exception as e:
        logger.error(f"Error in debug_test_models: {e}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat()
        }

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
        # Log detailed connection info
        logger.info(f"Attempting to fetch FAQs with skip={skip}, limit={limit}, active_only={active_only}")
        
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
    Get a specific FAQ item by ID.
    
    - **faq_id**: ID of the FAQ item
    """
    try:
        faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ item not found")
        return FAQResponse.model_validate(faq, from_attributes=True)
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
        
        # Sử dụng model_dump thay vì dict
        update_data = faq_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(faq, key, value)
            
        db.commit()
        db.refresh(faq)
        return FAQResponse.model_validate(faq, from_attributes=True)
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
        # Log detailed connection info
        logger.info(f"Attempting to fetch emergency contacts with skip={skip}, limit={limit}, active_only={active_only}")
        
        # Check if the EmergencyItem table exists
        inspector = inspect(db.bind)
        if not inspector.has_table("emergency_item"):
            logger.error("The emergency_item table does not exist in the database")
            raise HTTPException(status_code=500, detail="Table 'emergency_item' does not exist")
        
        # Log table columns
        columns = inspector.get_columns("emergency_item")
        logger.info(f"emergency_item table columns: {[c['name'] for c in columns]}")
        
        # Try direct SQL to debug
        try:
            test_result = db.execute(text("SELECT COUNT(*) FROM emergency_item")).scalar()
            logger.info(f"SQL test query succeeded, found {test_result} emergency contacts")
        except Exception as sql_error:
            logger.error(f"SQL test query failed: {sql_error}")
        
        # Query the emergency contacts
        query = db.query(EmergencyItem)
        if active_only:
            query = query.filter(EmergencyItem.is_active == True)
        
        # Execute the ORM query
        emergency_contacts = query.offset(skip).limit(limit).all()
        logger.info(f"Successfully fetched {len(emergency_contacts)} emergency contacts")
        
        # Check what we're returning
        for i, contact in enumerate(emergency_contacts[:3]):  # Log the first 3 items
            logger.info(f"Emergency contact {i+1}: id={contact.id}, name={contact.name}")
        
        return emergency_contacts
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
        # Log detailed connection info
        logger.info(f"Attempting to fetch events with skip={skip}, limit={limit}, active_only={active_only}, featured_only={featured_only}")
        
        # Check if the EventItem table exists
        inspector = inspect(db.bind)
        if not inspector.has_table("event_item"):
            logger.error("The event_item table does not exist in the database")
            raise HTTPException(status_code=500, detail="Table 'event_item' does not exist")
        
        # Log table columns
        columns = inspector.get_columns("event_item")
        logger.info(f"event_item table columns: {[c['name'] for c in columns]}")
        
        # Try direct SQL to debug
        try:
            test_result = db.execute(text("SELECT COUNT(*) FROM event_item")).scalar()
            logger.info(f"SQL test query succeeded, found {test_result} events")
        except Exception as sql_error:
            logger.error(f"SQL test query failed: {sql_error}")
        
        # Query the events
        query = db.query(EventItem)
        if active_only:
            query = query.filter(EventItem.is_active == True)
        if featured_only:
            query = query.filter(EventItem.featured == True)
        
        # Execute the ORM query
        events = query.offset(skip).limit(limit).all()
        logger.info(f"Successfully fetched {len(events)} events")
        
        # Debug price field of first event
        if events and len(events) > 0:
            logger.info(f"First event price type: {type(events[0].price)}, value: {events[0].price}")
        
        # Check what we're returning
        for i, event in enumerate(events[:3]):  # Log the first 3 items
            logger.info(f"Event {i+1}: id={event.id}, name={event.name}, price={type(event.price)}")
        
        return events
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
        # Use text() to wrap the SQL query for SQLAlchemy 2.0 compatibility
        db.execute(text("SELECT 1")).first()
        return {"status": "healthy", "message": "PostgreSQL connection is working", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"PostgreSQL connection failed: {str(e)}") 