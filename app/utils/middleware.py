from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import time
import traceback
import uuid
from .utils import get_local_time

# Configure logging
logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log requests and responses"""
    
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Log request information
        client_host = request.client.host if request.client else "unknown"
        logger.info(f"Request [{request_id}]: {request.method} {request.url.path} from {client_host}")
        
        # Measure processing time
        start_time = time.time()
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            logger.info(f"Response [{request_id}]: {response.status_code} processed in {process_time:.4f}s")
            
            # Add headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            # Log error
            process_time = time.time() - start_time
            logger.error(f"Error [{request_id}] after {process_time:.4f}s: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Return error response
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                    "timestamp": get_local_time()
                }
            )

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware to handle uncaught exceptions in the application"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            # Get request_id if available
            request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
            
            # Log error
            logger.error(f"Uncaught exception [{request_id}]: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Return error response
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                    "timestamp": get_local_time()
                }
            )

class DatabaseCheckMiddleware(BaseHTTPMiddleware):
    """Middleware to check database connections before each request"""
    
    async def dispatch(self, request: Request, call_next):
        # Skip paths that don't need database checks
        skip_paths = ["/", "/health", "/docs", "/redoc", "/openapi.json"]
        if request.url.path in skip_paths:
            return await call_next(request)
        
        # Check database connections
        try:
            # TODO: Add checks for MongoDB and Pinecone if needed
            # PostgreSQL check is already done in route handler with get_db() method
            
            # Process request normally
            return await call_next(request)
            
        except Exception as e:
            # Log error
            logger.error(f"Database connection check failed: {str(e)}")
            
            # Return error response
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "detail": "Database connection failed",
                    "timestamp": get_local_time()
                }
            ) 