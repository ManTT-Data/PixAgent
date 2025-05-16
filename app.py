from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import os
import sys
import logging
from dotenv import load_dotenv
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import time
import uuid
import traceback

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

# Kiểm tra các biến môi trường bắt buộc
required_env_vars = [
    "AIVEN_DB_URL", 
    "MONGODB_URL", 
    "PINECONE_API_KEY", 
    "PINECONE_INDEX_NAME", 
    "GOOGLE_API_KEY"
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    if not DEBUG:  # Chỉ thoát nếu không ở chế độ debug
        sys.exit(1)

# Database health checks
def check_database_connections():
    """Kiểm tra kết nối các database khi khởi động"""
    from app.database.postgresql import check_db_connection as check_postgresql
    from app.database.mongodb import check_db_connection as check_mongodb
    from app.database.pinecone import check_db_connection as check_pinecone
    
    db_status = {
        "postgresql": check_postgresql(),
        "mongodb": check_mongodb(),
        "pinecone": check_pinecone()
    }
    
    all_ok = all(db_status.values())
    if not all_ok:
        failed_dbs = [name for name, status in db_status.items() if not status]
        logger.error(f"Failed to connect to databases: {', '.join(failed_dbs)}")
        if not DEBUG:  # Chỉ thoát nếu không ở chế độ debug
            sys.exit(1)
    
    return db_status

# Khởi tạo lifespan để kiểm tra kết nối database khi khởi động
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: kiểm tra kết nối các database
    logger.info("Starting application...")
    db_status = check_database_connections()
    
    # Khởi tạo bảng trong cơ sở dữ liệu (nếu chưa tồn tại)
    if DEBUG and all(db_status.values()):  # Chỉ khởi tạo bảng trong chế độ debug và khi tất cả kết nối DB thành công
        from app.database.postgresql import create_tables
        if create_tables():
            logger.info("Database tables created or already exist")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")

# Import routers
try:
    from app.api.mongodb_routes import router as mongodb_router
    from app.api.postgresql_routes import router as postgresql_router
    from app.api.rag_routes import router as rag_router
    from app.api.websocket_routes import router as websocket_router
    from app.api.pdf_routes import router as pdf_router
    from app.api.pdf_websocket import router as pdf_websocket_router
    
    # Import middlewares
    from app.utils.middleware import RequestLoggingMiddleware, ErrorHandlingMiddleware, DatabaseCheckMiddleware
    
    # Import debug utilities
    from app.utils.debug_utils import debug_view, DebugInfo, error_tracker, performance_monitor
    
    # Import cache
    from app.utils.cache import get_cache
    
    logger.info("Successfully imported all routers and modules")
    
except ImportError as e:
    logger.error(f"Error importing routes or middlewares: {e}")
    raise

# Create FastAPI app
app = FastAPI(
    title="PIX Project Backend API",
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

# Thêm middlewares
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
if not DEBUG:  # Chỉ thêm middleware kiểm tra database trong production
    app.add_middleware(DatabaseCheckMiddleware)

# Include routers
app.include_router(mongodb_router)
app.include_router(postgresql_router)
app.include_router(rag_router)
app.include_router(websocket_router)
app.include_router(pdf_router)
app.include_router(pdf_websocket_router)

# Log all registered routes
logger.info("Registered API routes:")
for route in app.routes:
    if hasattr(route, "path") and hasattr(route, "methods"):
        methods = ",".join(route.methods)
        logger.info(f"  {methods:<10} {route.path}")

# Root endpoint
@app.get("/")
def read_root():
    return {
        "message": "Welcome to PIX Project Backend API",
        "documentation": "/docs",
    }

# Health check endpoint
@app.get("/health")
def health_check():
    # Kiểm tra kết nối database
    db_status = check_database_connections()
    all_db_ok = all(db_status.values())
    
    return {
        "status": "healthy" if all_db_ok else "degraded",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "production"),
        "databases": db_status
    }

@app.get("/api/ping")
async def ping():
    return {"status": "pong"}

# Cache stats endpoint
@app.get("/cache/stats")
def cache_stats():
    """Trả về thống kê về cache"""
    cache = get_cache()
    return cache.stats()

# Cache clear endpoint
@app.delete("/cache/clear")
def cache_clear():
    """Xóa tất cả dữ liệu trong cache"""
    cache = get_cache()
    cache.clear()
    return {"message": "Cache cleared successfully"}

# Debug endpoints (chỉ có trong chế độ debug)
if DEBUG:
    @app.get("/debug/config")
    def debug_config():
        """Hiển thị thông tin cấu hình (chỉ trong chế độ debug)"""
        config = {
            "environment": os.environ.get("ENVIRONMENT", "production"),
            "debug": DEBUG,
            "db_connection_mode": os.environ.get("DB_CONNECTION_MODE", "aiven"),
            "databases": {
                "postgresql": os.environ.get("AIVEN_DB_URL", "").split("@")[1].split("/")[0] if "@" in os.environ.get("AIVEN_DB_URL", "") else "N/A",
                "mongodb": os.environ.get("MONGODB_URL", "").split("@")[1].split("/?")[0] if "@" in os.environ.get("MONGODB_URL", "") else "N/A",
                "pinecone": os.environ.get("PINECONE_INDEX_NAME", "N/A"),
            }
        }
        return config
    
    @app.get("/debug/system")
    def debug_system():
        """Hiển thị thông tin hệ thống (chỉ trong chế độ debug)"""
        return DebugInfo.get_system_info()
    
    @app.get("/debug/database")
    def debug_database():
        """Hiển thị trạng thái database (chỉ trong chế độ debug)"""
        return DebugInfo.get_database_status()
    
    @app.get("/debug/errors")
    def debug_errors(limit: int = 10):
        """Hiển thị các lỗi gần đây (chỉ trong chế độ debug)"""
        return error_tracker.get_errors(limit=limit)
    
    @app.get("/debug/performance")
    def debug_performance():
        """Hiển thị thông tin hiệu suất (chỉ trong chế độ debug)"""
        return performance_monitor.get_report()
    
    @app.get("/debug/full")
    def debug_full_report(request: Request):
        """Hiển thị báo cáo debug đầy đủ (chỉ trong chế độ debug)"""
        return debug_view(request)
    
    @app.get("/debug/cache")
    def debug_cache():
        """Hiển thị thông tin chi tiết về cache (chỉ trong chế độ debug)"""
        cache = get_cache()
        cache_stats = cache.stats()
        
        # Thêm thông tin chi tiết về các key trong cache
        cache_keys = list(cache.cache.keys())
        history_users = list(cache.user_history_queues.keys())
        
        return {
            "stats": cache_stats,
            "keys": cache_keys,
            "history_users": history_users,
            "config": {
                "ttl": cache.ttl,
                "cleanup_interval": cache.cleanup_interval,
                "max_size": cache.max_size,
                "history_queue_size": os.getenv("HISTORY_QUEUE_SIZE", "10"),
                "history_cache_ttl": os.getenv("HISTORY_CACHE_TTL", "3600"),
            }
        }
    
    @app.get("/debug/websocket-routes")
    def debug_websocket_routes():
        """Hiển thị thông tin về các WebSocket route (chỉ trong chế độ debug)"""
        ws_routes = []
        for route in app.routes:
            if "websocket" in str(route.__class__).lower():
                ws_routes.append({
                    "path": route.path,
                    "name": route.name,
                    "endpoint": str(route.endpoint)
                })
        return {
            "websocket_routes": ws_routes,
            "total_count": len(ws_routes)
        }
        
    @app.get("/debug/mock-status")
    def debug_mock_status():
        """Display current mock mode settings"""
        # Import was: from app.api.pdf_routes import USE_MOCK_MODE
        # We've disabled mock mode
        
        return {
            "mock_mode": False,  # Disabled - using real database
            "mock_env_variable": os.getenv("USE_MOCK_MODE", "false"),
            "debug_mode": DEBUG
        }

# Add new debug endpoint for Pinecone connection
@app.get("/debug/pinecone-check")
async def debug_pinecone_connection():
    """Check Pinecone connection and API key status"""
    try:
        # Import settings and pinecone client
        from app.utils.pdf_processor import PDFProcessor
        from app.database.pinecone import get_pinecone_index
        
        # Get settings
        pinecone_settings = get_pinecone_settings()
        
        # Try to get an API key from the database
        api_key = None
        vector_db_id = None
        
        try:
            from app.database.postgresql import get_db
            from app.database.models import VectorDatabase
            
            # Get first active vector database
            db = next(get_db())
            vector_db = db.query(VectorDatabase).filter(
                VectorDatabase.status == "active"
            ).first()
            
            if vector_db:
                vector_db_id = vector_db.id
                
                # Get API key from relationship if available
                if hasattr(vector_db, 'api_key_ref') and vector_db.api_key_ref:
                    api_key = vector_db.api_key_ref.key_value
                    api_key_source = "from relationship"
                else:
                    api_key_source = "not found in relationship"
            else:
                api_key_source = "no active vector database found"
        except Exception as db_error:
            logger.error(f"Error accessing database: {db_error}")
            api_key_source = f"error: {str(db_error)}"
        
        # Direct environment check
        env_api_key = os.environ.get("PINECONE_API_KEY", "Not set")
        api_key_prefix = env_api_key[:4] + "..." if env_api_key != "Not set" else "Not set"
        
        # Test connection using PDFProcessor
        connection_test = None
        try:
            if vector_db_id:
                processor = PDFProcessor(
                    api_key=None,
                    vector_db_id=vector_db_id, 
                    mock_mode=False
                )
                index = processor._init_pinecone_connection()
                
                if index:
                    connection_test = "Success with vector_db_id"
                    
                    # Try to get stats
                    try:
                        stats = index.describe_index_stats()
                        index_stats = {
                            "total_vectors": stats.get("total_vector_count", 0),
                            "namespaces": list(stats.get("namespaces", {}).keys())
                        }
                    except Exception as stats_error:
                        index_stats = {"error": str(stats_error)}
                else:
                    connection_test = "Failed with vector_db_id"
                    index_stats = None
            else:
                connection_test = "No vector_db_id available"
                index_stats = None
        except Exception as conn_error:
            connection_test = f"Error: {str(conn_error)}"
            index_stats = None
        
        # Return all relevant information
        return {
            "pinecone_settings": {
                "environment": pinecone_settings.environment,
                "index_name": pinecone_settings.index_name,
            },
            "api_key_status": {
                "environment_key_prefix": api_key_prefix,
                "db_key_available": api_key is not None,
                "api_key_source": api_key_source
            },
            "connection_test": connection_test,
            "index_stats": index_stats,
            "vector_db_id": vector_db_id
        }
    except Exception as e:
        logger.error(f"Error in pinecone-check endpoint: {e}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }

# Run the app with uvicorn when executed directly
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=DEBUG) 
