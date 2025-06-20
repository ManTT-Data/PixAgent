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

# Configure logging
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

# Check required environment variables
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
    if not DEBUG:  # Only exit if not in debug mode
        sys.exit(1)

# Database health checks
def check_database_connections():
    """Check database connections on startup"""
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
        if not DEBUG:  # Only exit if not in debug mode
            sys.exit(1)
    
    return db_status

# Initialize lifespan to check database connections on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: check database connections
    logger.info("Starting application...")
    try:
        db_status = check_database_connections()
        
        # Initialize tables in database (if they don't exist)
        if DEBUG and all(db_status.values()):
            from app.database.postgresql import create_tables
            if create_tables():
                logger.info("Database tables created or already exist")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        if not DEBUG:
            raise
    
    yield
    
    # Shutdown: cleanup connections
    logger.info("Shutting down application...")
    try:
        from app.database.postgresql import engine
        engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Import routers
try:
    from app.api.mongodb_routes import router as mongodb_router
    from app.api.postgresql_routes import router as postgresql_router
    from app.api.rag_routes import router as rag_router
    from app.api.websocket_routes import router as websocket_router
    from app.api.pdf_routes import router as pdf_router
    from app.api.pdf_websocket import router as pdf_websocket_router
    from app.api.admin_routes import router as admin_router
    from app.api.content_routes import router as content_router
    
    # Import middlewares
    from app.utils.middleware import RequestLoggingMiddleware, ErrorHandlingMiddleware, DatabaseCheckMiddleware
    from app.middleware.admin_logging import AdminLoggingMiddleware
    
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

# Add middlewares in correct order
if not DEBUG:  # Only add database check middleware in production
    app.add_middleware(DatabaseCheckMiddleware)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(AdminLoggingMiddleware)

# Include routers
app.include_router(mongodb_router)
app.include_router(postgresql_router)
app.include_router(rag_router)
app.include_router(websocket_router)
app.include_router(pdf_router)
app.include_router(pdf_websocket_router)
app.include_router(admin_router)
app.include_router(content_router)

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
    # Check database connections
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
    """Return cache statistics"""
    cache = get_cache()
    return cache.stats()

# Cache clear endpoint
@app.delete("/cache/clear")
def cache_clear():
    """Clear all data in cache"""
    cache = get_cache()
    cache.clear()
    return {"message": "Cache cleared successfully"}

# Debug endpoints (only in debug mode)
if DEBUG:
    @app.get("/debug/config")
    def debug_config():
        """Display configuration information (debug mode only)"""
        config = {
            "environment": os.environ.get("ENVIRONMENT", "production"),
            "debug": DEBUG,
            "db_connection_mode": os.environ.get("DB_CONNECTION_MODE", "aiven"),
            "databases": {
                "postgresql": os.environ.get("AIVEN_DB_URL", "").split("@")[1].split("/")[0] if "@" in os.environ.get("AIVEN_DB_URL", "") else "N/A",
                "mongodb": os.environ.get("MONGODB_URL", "").split("@")[1].split("/")[0] if "@" in os.environ.get("MONGODB_URL", "") else "N/A",
                "pinecone": "configured" if os.environ.get("PINECONE_API_KEY") else "not configured"
            }
        }
        return config

    @app.get("/debug/system")
    def debug_system():
        """Display system information (debug mode only)"""
        return debug_view.get_system_info()

    @app.get("/debug/database")
    def debug_database():
        """Display database information (debug mode only)"""
        return debug_view.get_database_info()

    @app.get("/debug/errors")
    def debug_errors(limit: int = 10):
        """Display recent errors (debug mode only)"""
        return error_tracker.get_recent_errors(limit)

    @app.get("/debug/performance")
    def debug_performance():
        """Display performance metrics (debug mode only)"""
        return performance_monitor.get_metrics()

    @app.get("/debug/full")
    def debug_full_report(request: Request):
        """Generate full debug report (debug mode only)"""
        return debug_view.generate_full_report(request)

    @app.get("/debug/cache")
    def debug_cache():
        """Display cache information (debug mode only)"""
        cache = get_cache()
        return {
            "stats": cache.stats(),
            "info": cache.info(),
            "keys": list(cache.keys())
        }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=DEBUG) 
