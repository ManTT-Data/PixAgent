import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from dotenv import load_dotenv
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get DB connection mode from environment
DB_CONNECTION_MODE = os.getenv("DB_CONNECTION_MODE", "aiven")

# Set connection string based on mode
if DB_CONNECTION_MODE == "aiven":
    DATABASE_URL = os.getenv("AIVEN_DB_URL")
else:
    # Default or other connection modes can be added here
    DATABASE_URL = os.getenv("AIVEN_DB_URL")

if not DATABASE_URL:
    logger.error("No database URL configured. Please set AIVEN_DB_URL environment variable.")
    DATABASE_URL = "postgresql://localhost/test"  # Fallback to avoid crash on startup

# Create SQLAlchemy engine with optimized settings
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,         # Enable connection health checks
        pool_recycle=300,           # Recycle connections every 5 minutes
        pool_size=20,               # Increase pool size for more concurrent connections
        max_overflow=30,            # Allow more overflow connections
        pool_timeout=30,            # Timeout for getting connection from pool
        connect_args={
            "connect_timeout": 5,   # Connection timeout in seconds
            "keepalives": 1,        # Enable TCP keepalives
            "keepalives_idle": 30,  # Time before sending keepalives
            "keepalives_interval": 10, # Time between keepalives
            "keepalives_count": 5,  # Number of keepalive probes
            "application_name": "pixagent_api" # Identify app in PostgreSQL logs
        },
        # Performance optimizations
        isolation_level="READ COMMITTED",  # Lower isolation level for better performance
        echo=False,                 # Disable SQL echo to reduce overhead
        echo_pool=False,            # Disable pool logging
        future=True,                # Use SQLAlchemy 2.0 features
        # Execution options for common queries
        execution_options={
            "compiled_cache": {},   # Use an empty dict for compiled query caching
            "logging_token": "SQL", # Tag for query logging
        }
    )
    logger.info("PostgreSQL engine initialized with optimized settings")
except Exception as e:
    logger.error(f"Failed to initialize PostgreSQL engine: {e}")
    # Don't raise exception to avoid crash on startup

# Create optimized session factory
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    expire_on_commit=False  # Prevent automatic reloading after commit
)

# Base class for declarative models - use sqlalchemy.orm for SQLAlchemy 2.0 compatibility
from sqlalchemy.orm import declarative_base
Base = declarative_base()

# Check PostgreSQL connection
def check_db_connection():
    """Check PostgreSQL connection status"""
    try:
        # Simple query to verify connection
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).fetchone()
        logger.info("PostgreSQL connection successful")
        return True
    except OperationalError as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unknown error checking PostgreSQL connection: {e}")
        return False

# Dependency to get DB session with improved error handling
def get_db():
    """Get database session dependency for FastAPI endpoints"""
    db = SessionLocal()
    try:
        # Test connection is valid before returning
        db.execute(text("SELECT 1")).fetchone()
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

# Create tables in database if they don't exist
def create_tables():
    """Create tables in database"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created or already exist")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Failed to create database tables (SQLAlchemy error): {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to create database tables (unexpected error): {e}")
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