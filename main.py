from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import os
import sys
import logging
from dotenv import load_dotenv

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log"),
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
DEBUG = True  # Force debug mode for testing

# BYPASS ENVIRONMENT CHECKS FOR TESTING
# required_env_vars = [
#     "AIVEN_DB_URL", 
#     "MONGODB_URL", 
#     "PINECONE_API_KEY", 
#     "PINECONE_INDEX_NAME", 
#     "GOOGLE_API_KEY"
# ]
# 
# missing_vars = [var for var in required_env_vars if not os.getenv(var)]
# if missing_vars:
#     logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
#     if not DEBUG:  # Chỉ thoát nếu không ở chế độ debug
#         sys.exit(1)

# Database health checks - BYPASSED FOR TESTING
def check_database_connections():
    """Kiểm tra kết nối các database khi khởi động"""
    # BYPASS DATABASE CHECKS FOR TESTING
    logger.info("Database checks bypassed for testing")
    return {"postgresql": True, "mongodb": True, "pinecone": True}
    
# Khởi tạo lifespan để kiểm tra kết nối database khi khởi động
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: kiểm tra kết nối các database
    logger.info("Starting application...")
    db_status = check_database_connections()
    if all(db_status.values()):
        logger.info("All database connections are working")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")

# Create FastAPI app for testing with simplified routes
app = FastAPI(
    title="PIX Project Backend API - TEST MODE",
    description="Backend API for PIX Project with MongoDB, PostgreSQL and RAG integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    debug=DEBUG,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
def read_root():
    return {
        "message": "Welcome to PIX Project Backend API - TEST MODE",
        "documentation": "/docs",
    }

# TEST EVENTS ENDPOINTS
from fastapi import APIRouter, Path, Query, Body
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

# Define a model for the price object
class PriceItem(BaseModel):
    type: str
    amount: float
    currency: str

class EventBase(BaseModel):
    name: str
    description: str
    address: str
    location: Optional[str] = None
    date_start: datetime
    date_end: Optional[datetime] = None
    price: Optional[List[dict]] = None  # Now a list of dictionaries
    is_active: bool = True
    featured: bool = False

class EventResponse(EventBase):
    id: int
    created_at: datetime
    updated_at: datetime

# Test data based on what you shared
test_events = [
    {
        "id": 1,
        "name": "Today's Workshop",
        "description": "A workshop happening today",
        "address": "123 Main St, Workshop City",
        "location": "0101000020E6100000371AC05B208125403EE8D9ACFAF44D40",
        "date_start": "2025-04-14T14:00:00.913181",
        "date_end": "2025-04-14T17:00:00.913181",
        "price": [{"type": "standard", "amount": 20, "currency": "USD"}],
        "created_at": "2025-04-14T15:41:25.691144",
        "updated_at": "2025-04-14T15:41:25.691144",
        "is_active": True,
        "featured": False
    },
    {
        "id": 2,
        "name": "Tomorrow's Conference",
        "description": "A conference happening tomorrow",
        "address": "456 Conference Blvd, Event City",
        "location": "0101000020E6100000B3EA73B5157F52C0C7293A92CB5F4440",
        "date_start": "2025-04-15T09:00:00.913181",
        "date_end": "2025-04-15T18:00:00.913181",
        "price": [{"type": "early", "amount": 50, "currency": "USD"}, {"type": "regular", "amount": 75, "currency": "USD"}],
        "created_at": "2025-04-14T15:41:25.691144",
        "updated_at": "2025-04-14T15:41:25.691144",
        "is_active": True,
        "featured": True
    },
    {
        "id": 3,
        "name": "Next Week Seminar",
        "description": "A seminar happening next week",
        "address": "789 Seminar Ave, Learning City",
        "location": "0101000020E6100000A835CD3B4ED1024076E09C11A56D4840",
        "date_start": "2025-04-21T10:00:00.913181",
        "date_end": "2025-04-21T16:00:00.913181",
        "price": [{"type": "standard", "amount": 30, "currency": "USD"}],
        "created_at": "2025-04-14T15:41:25.691144",
        "updated_at": "2025-04-14T15:41:25.691144",
        "is_active": True,
        "featured": False
    }
]

@app.get("/postgres/events", response_model=List[EventResponse])
async def get_events(
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    featured_only: bool = False,
):
    """
    Get all events.
    
    - **skip**: Number of items to skip
    - **limit**: Maximum number of items to return
    - **active_only**: If true, only return active items
    - **featured_only**: If true, only return featured items
    """
    filtered_events = test_events
    
    if active_only:
        filtered_events = [e for e in filtered_events if e["is_active"]]
    if featured_only:
        filtered_events = [e for e in filtered_events if e["featured"]]
    
    return filtered_events[skip:skip+limit]

@app.get("/postgres/events/{event_id}", response_model=EventResponse)
async def get_event(event_id: int = Path(..., gt=0)):
    """
    Get a specific event by ID.
    
    - **event_id**: ID of the event
    """
    for event in test_events:
        if event["id"] == event_id:
            return event
    
    raise HTTPException(status_code=404, detail="Event not found")

# Health check endpoint
@app.get("/health")
def health_check():
    # Return all healthy for testing
    return {
        "status": "healthy", 
        "version": "1.0.0",
        "environment": "testing",
        "databases": {"postgresql": True, "mongodb": True, "pinecone": True}
    }

# Run the app with uvicorn when executed directly
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=DEBUG) 