import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from dotenv import load_dotenv
import logging
from sqlalchemy.pool import QueuePool

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Define default PostgreSQL connection string
DEFAULT_DB_URL = os.getenv("AIVEN_DB_URL")  
# Set the default DB URL with the correct domain (.l.)
# Get DB connection mode from environment
DB_CONNECTION_MODE = os.getenv("DB_CONNECTION_MODE", "aiven")

# Set connection string based on mode
if DB_CONNECTION_MODE == "aiven":
    DATABASE_URL = os.getenv("AIVEN_DB_URL", DEFAULT_DB_URL)
else:
    # Default or other connection modes can be added here
    DATABASE_URL = os.getenv("AIVEN_DB_URL", DEFAULT_DB_URL)

if not DATABASE_URL:
    logger.error("No database URL configured. Using default URL.")
    DATABASE_URL = DEFAULT_DB_URL  # Use the correct default URL

# Configure the database engine with proper pooling
try:
    engine = create_engine(
        DATABASE_URL,
        pool_size=2,  # Maximum number of permanent connections
        max_overflow=20,  # Maximum number of additional connections
        pool_timeout=30,  # Timeout in seconds for getting a connection from the pool
        pool_recycle=300,  # Recycle connections after 30 minutes
        pool_pre_ping=True,  # Enable connection health checks
        poolclass=QueuePool,  # Use QueuePool for better connection management
        echo=True  # Enable SQL query logging
    )
    
    # Test the connection
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        logger.info("Successfully connected to PostgreSQL database")
except Exception as e:
    logger.error(f"Failed to create database engine: {e}")
    raise

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for declarative models
Base = declarative_base()

# Check PostgreSQL connection
def check_db_connection():
    """Check if database connection is working."""
    try:
        # Create a new connection and immediately close it
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                return True
            else:
                logger.error("Database connection check failed: unexpected result")
                return False
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False

# Dependency to get DB session with improved error handling
def get_db():
    """Get database session with proper cleanup."""
    db = None
    try:
        db = SessionLocal()
        # Test the connection
        db.execute(text("SELECT 1"))
        yield db
    except Exception as e:
        logger.error(f"Error getting database session: {e}")
        if db:
            db.rollback()
        raise
    finally:
        if db:
            db.close()

# Create tables in database if they don't exist
def create_tables():
    """Create all tables in database."""
    try:
        Base.metadata.create_all(bind=engine)
        return True
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        return False

# Function to create indexes for better performance
def create_indexes():
    """Create indexes for better query performance"""
    try:
        with engine.connect() as conn:
            try:
                # Index for featured events - use try-except to handle if index already exists
                conn.execute(text("""
                    CREATE INDEX idx_event_featured 
                    ON event_item(featured)
                """))
            except SQLAlchemyError:
                logger.info("Index idx_event_featured already exists")
            
            try:
                # Index for active events
                conn.execute(text("""
                    CREATE INDEX idx_event_active 
                    ON event_item(is_active)
                """))
            except SQLAlchemyError:
                logger.info("Index idx_event_active already exists")
            
            try:
                # Index for date filtering
                conn.execute(text("""
                    CREATE INDEX idx_event_date_start 
                    ON event_item(date_start)
                """))
            except SQLAlchemyError:
                logger.info("Index idx_event_date_start already exists")
            
            try:
                # Composite index for combined filtering
                conn.execute(text("""
                    CREATE INDEX idx_event_featured_active 
                    ON event_item(featured, is_active)
                """))
            except SQLAlchemyError:
                logger.info("Index idx_event_featured_active already exists")
                
            # Indexes for FAQ and Emergency tables
            try:
                # FAQ active flag index
                conn.execute(text("""
                    CREATE INDEX idx_faq_active 
                    ON faq_item(is_active)
                """))
            except SQLAlchemyError:
                logger.info("Index idx_faq_active already exists")
            
            try:
                # Emergency contact active flag and priority indexes
                conn.execute(text("""
                    CREATE INDEX idx_emergency_active 
                    ON emergency_item(is_active)
                """))
            except SQLAlchemyError:
                logger.info("Index idx_emergency_active already exists")
                
            try:
                conn.execute(text("""
                    CREATE INDEX idx_emergency_priority 
                    ON emergency_item(priority)
                """))
            except SQLAlchemyError:
                logger.info("Index idx_emergency_priority already exists")
            
            conn.commit()
            
        logger.info("Database indexes created or verified")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Failed to create indexes: {e}")
        return False 