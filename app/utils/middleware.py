from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import time
import traceback
import uuid
from .utils import get_vietnam_time

# Cấu hình logging
logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware để ghi log các request và response"""
    
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Ghi log thông tin request
        client_host = request.client.host if request.client else "unknown"
        logger.info(f"Request [{request_id}]: {request.method} {request.url.path} from {client_host}")
        
        # Đo thời gian xử lý
        start_time = time.time()
        
        try:
            # Xử lý request
            response = await call_next(request)
            
            # Tính thời gian xử lý
            process_time = time.time() - start_time
            logger.info(f"Response [{request_id}]: {response.status_code} processed in {process_time:.4f}s")
            
            # Thêm headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            # Ghi log lỗi
            process_time = time.time() - start_time
            logger.error(f"Error [{request_id}] after {process_time:.4f}s: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Trả về response lỗi
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                    "timestamp": get_vietnam_time()
                }
            )

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware để xử lý các lỗi không được bắt trong ứng dụng"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            # Lấy request_id nếu có
            request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
            
            # Ghi log lỗi
            logger.error(f"Uncaught exception [{request_id}]: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Trả về response lỗi
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                    "timestamp": get_vietnam_time()
                }
            )

class DatabaseCheckMiddleware(BaseHTTPMiddleware):
    """Middleware để kiểm tra kết nối database trước mỗi request"""
    
    async def dispatch(self, request: Request, call_next):
        # Bỏ qua các routes không cần kiểm tra database
        skip_paths = ["/", "/health", "/docs", "/redoc", "/openapi.json"]
        if request.url.path in skip_paths:
            return await call_next(request)
        
        # Kiểm tra database connections
        try:
            # TODO: Thêm các kiểm tra đối với MongoDB và Pinecone nếu cần
            # Việc kiểm tra PostgreSQL đã được thực hiện ở route handler với phương thức get_db()
            
            # Xử lý request bình thường
            return await call_next(request)
            
        except Exception as e:
            # Ghi log lỗi
            logger.error(f"Database connection check failed: {str(e)}")
            
            # Trả về response lỗi
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "detail": "Database connection failed",
                    "timestamp": get_vietnam_time()
                }
            ) 