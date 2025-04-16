import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from dotenv import load_dotenv
import logging

# Cấu hình logging
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
    DATABASE_URL = "postgresql://localhost/test"  # Fallback để không crash khi khởi động

# Create SQLAlchemy engine
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,  # Recycle connections every 5 minutes
        pool_size=10,      # Tăng kích thước pool từ 5 lên 10
        max_overflow=20,   # Tăng số lượng kết nối tối đa từ 10 lên 20
        connect_args={
            "connect_timeout": 3,  # Giảm timeout từ 5 xuống 3 giây
            "keepalives": 1,      # Bật keepalive
            "keepalives_idle": 30, # Thời gian idle trước khi gửi keepalive
            "keepalives_interval": 10, # Khoảng thời gian giữa các gói keepalive
            "keepalives_count": 5  # Số lần thử lại trước khi đóng kết nối
        },
        # Thêm các tùy chọn hiệu suất
        isolation_level="READ COMMITTED",  # Mức cô lập thấp hơn READ COMMITTED
        echo=False,  # Tắt echo SQL để giảm overhead logging
        echo_pool=False  # Tắt echo pool để giảm overhead logging
    )
    logger.info("PostgreSQL engine initialized")
except Exception as e:
    logger.error(f"Failed to initialize PostgreSQL engine: {e}")
    # Không raise exception để tránh crash khi khởi động, các xử lý lỗi sẽ được thực hiện ở các function

# Create session factory with optimized settings
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    expire_on_commit=False  # Tránh truy vấn lại DB sau khi commit
)

# Base class for declarative models - use sqlalchemy.orm for SQLAlchemy 2.0 compatibility
from sqlalchemy.orm import declarative_base
Base = declarative_base()

# Kiểm tra kết nối PostgreSQL
def check_db_connection():
    """Kiểm tra kết nối PostgreSQL"""
    try:
        # Thực hiện một truy vấn đơn giản để kiểm tra kết nối
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection is working")
        return True
    except OperationalError as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unknown error when checking PostgreSQL connection: {e}")
        return False

# Dependency to get DB session
def get_db():
    """Get database session dependency for FastAPI endpoints"""
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

# Tạo các bảng trong cơ sở dữ liệu nếu chưa tồn tại
def create_tables():
    """Tạo các bảng trong cơ sở dữ liệu"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created or already exist")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Failed to create database tables: {e}")
        return False 