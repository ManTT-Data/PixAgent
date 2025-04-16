import os
import sys
import logging
import traceback
import json
import time
from datetime import datetime
import platform

# Cố gắng import psutil, nếu không có thì cung cấp phương án dự phòng
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil module not available. System monitoring features will be limited.")

# Cấu hình logging
logger = logging.getLogger(__name__)

class DebugInfo:
    """Lớp chứa các thông tin debug"""
    
    @staticmethod
    def get_system_info():
        """Lấy thông tin hệ thống"""
        try:
            info = {
                "os": platform.system(),
                "os_version": platform.version(),
                "python_version": platform.python_version(),
                "cpu_count": os.cpu_count(),
                "timestamp": datetime.now().isoformat()
            }
            
            # Thêm thông tin từ psutil nếu có sẵn
            if PSUTIL_AVAILABLE:
                info.update({
                    "total_memory": round(psutil.virtual_memory().total / (1024 * 1024 * 1024), 2),  # GB
                    "available_memory": round(psutil.virtual_memory().available / (1024 * 1024 * 1024), 2),  # GB
                    "cpu_usage": psutil.cpu_percent(interval=0.1),
                    "memory_usage": psutil.virtual_memory().percent,
                    "disk_usage": psutil.disk_usage('/').percent,
                })
            else:
                info.update({
                    "total_memory": "psutil not available",
                    "available_memory": "psutil not available",
                    "cpu_usage": "psutil not available",
                    "memory_usage": "psutil not available",
                    "disk_usage": "psutil not available",
                })
            
            return info
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def get_env_info():
        """Lấy thông tin biến môi trường (che giấu các thông tin nhạy cảm)"""
        try:
            # Danh sách các biến môi trường cần che giấu giá trị
            sensitive_vars = [
                "API_KEY", "SECRET", "PASSWORD", "TOKEN", "AUTH", "MONGODB_URL", 
                "AIVEN_DB_URL", "PINECONE_API_KEY", "GOOGLE_API_KEY"
            ]
            
            env_vars = {}
            for key, value in os.environ.items():
                # Kiểm tra xem biến môi trường có chứa từ nhạy cảm không
                is_sensitive = any(s in key.upper() for s in sensitive_vars)
                
                if is_sensitive and value:
                    # Che giấu giá trị chỉ hiển thị 4 ký tự đầu tiên
                    masked_value = value[:4] + "****" if len(value) > 4 else "****"
                    env_vars[key] = masked_value
                else:
                    env_vars[key] = value
                    
            return env_vars
        except Exception as e:
            logger.error(f"Error getting environment info: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def get_database_status():
        """Lấy trạng thái kết nối database"""
        try:
            from app.database.postgresql import check_db_connection as check_postgresql
            from app.database.mongodb import check_db_connection as check_mongodb
            from app.database.pinecone import check_db_connection as check_pinecone
            
            return {
                "postgresql": check_postgresql(),
                "mongodb": check_mongodb(),
                "pinecone": check_pinecone(),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting database status: {e}")
            return {"error": str(e)}

class PerformanceMonitor:
    """Lớp giám sát hiệu suất"""
    
    def __init__(self):
        self.start_time = time.time()
        self.checkpoints = []
    
    def checkpoint(self, name):
        """Đánh dấu một checkpoint và ghi lại thời gian"""
        current_time = time.time()
        elapsed = current_time - self.start_time
        self.checkpoints.append({
            "name": name,
            "time": current_time,
            "elapsed": elapsed
        })
        logger.debug(f"Checkpoint '{name}' at {elapsed:.4f}s")
        return elapsed
    
    def get_report(self):
        """Tạo báo cáo hiệu suất"""
        if not self.checkpoints:
            return {"error": "No checkpoints recorded"}
            
        total_time = time.time() - self.start_time
        
        # Tính thời gian giữa các checkpoint
        intervals = []
        prev_time = self.start_time
        
        for checkpoint in self.checkpoints:
            interval = checkpoint["time"] - prev_time
            intervals.append({
                "name": checkpoint["name"],
                "interval": interval,
                "elapsed": checkpoint["elapsed"]
            })
            prev_time = checkpoint["time"]
            
        return {
            "total_time": total_time,
            "checkpoint_count": len(self.checkpoints),
            "intervals": intervals
        }

class ErrorTracker:
    """Lớp theo dõi và ghi lại lỗi"""
    
    def __init__(self, max_errors=100):
        self.errors = []
        self.max_errors = max_errors
    
    def track_error(self, error, context=None):
        """Ghi lại thông tin lỗi"""
        error_info = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat(),
            "context": context or {}
        }
        
        # Thêm vào danh sách lỗi
        self.errors.append(error_info)
        
        # Giới hạn số lượng lỗi được lưu trữ
        if len(self.errors) > self.max_errors:
            self.errors.pop(0)  # Loại bỏ lỗi cũ nhất
            
        return error_info
    
    def get_errors(self, limit=None):
        """Lấy danh sách lỗi đã ghi lại"""
        if limit is None or limit >= len(self.errors):
            return self.errors
        return self.errors[-limit:]  # Trả về các lỗi gần đây nhất

# Khởi tạo các đối tượng global
error_tracker = ErrorTracker()
performance_monitor = PerformanceMonitor()

def debug_view(request=None):
    """Tạo báo cáo debug đầy đủ"""
    debug_data = {
        "system_info": DebugInfo.get_system_info(),
        "database_status": DebugInfo.get_database_status(),
        "performance": performance_monitor.get_report(),
        "recent_errors": error_tracker.get_errors(limit=10),
        "timestamp": datetime.now().isoformat()
    }
    
    # Thêm thông tin request nếu có
    if request:
        debug_data["request"] = {
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "client": {
                "host": request.client.host if request.client else "unknown",
                "port": request.client.port if request.client else "unknown"
            }
        }
    
    return debug_data 