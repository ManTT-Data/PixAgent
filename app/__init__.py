# PIX Project Backend
# Version: 1.0.0

__version__ = "1.0.0"

# Import app từ app.py để tests có thể tìm thấy
import sys
import os

# Thêm thư mục gốc vào sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Sử dụng importlib để tránh circular import
import importlib.util
spec = importlib.util.spec_from_file_location("app_module", 
                                             os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                                         "app.py"))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
app = app_module.app 
