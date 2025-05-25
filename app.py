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


# Run the app with uvicorn when executed directly
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=DEBUG) 
