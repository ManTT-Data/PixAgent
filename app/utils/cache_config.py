"""
Module cấu hình cho cache.

Module này chứa các tham số cấu hình và constants liên quan đến cache.
"""

import os
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv()

# Cấu hình cache từ biến môi trường, có thể override bằng .env file
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # Mặc định 5 phút
CACHE_CLEANUP_INTERVAL = int(os.getenv("CACHE_CLEANUP_INTERVAL", "60"))  # Mặc định 1 phút
CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "1000"))  # Mặc định 1000 phần tử

# Cấu hình cho loại cache cụ thể
CHAT_ENGINE_CACHE_TTL = int(os.getenv("CHAT_ENGINE_CACHE_TTL", str(CACHE_TTL_SECONDS)))
MODEL_CONFIG_CACHE_TTL = int(os.getenv("MODEL_CONFIG_CACHE_TTL", str(CACHE_TTL_SECONDS)))
RETRIEVER_CACHE_TTL = int(os.getenv("RETRIEVER_CACHE_TTL", str(CACHE_TTL_SECONDS)))
PROMPT_TEMPLATE_CACHE_TTL = int(os.getenv("PROMPT_TEMPLATE_CACHE_TTL", str(CACHE_TTL_SECONDS)))

# Cache keys prefix
CHAT_ENGINE_CACHE_PREFIX = "chat_engine:"
MODEL_CONFIG_CACHE_PREFIX = "model_config:"
RETRIEVER_CACHE_PREFIX = "retriever:"
PROMPT_TEMPLATE_CACHE_PREFIX = "prompt_template:"

# Hàm helper để tạo cache key
def get_chat_engine_cache_key(engine_id: int) -> str:
    """Tạo cache key cho chat engine"""
    return f"{CHAT_ENGINE_CACHE_PREFIX}{engine_id}"

def get_model_config_cache_key(model_name: str) -> str:
    """Tạo cache key cho model config"""
    return f"{MODEL_CONFIG_CACHE_PREFIX}{model_name}"

def get_retriever_cache_key(engine_id: int) -> str:
    """Tạo cache key cho retriever"""
    return f"{RETRIEVER_CACHE_PREFIX}{engine_id}"

def get_prompt_template_cache_key(engine_id: int) -> str:
    """Tạo cache key cho prompt template"""
    return f"{PROMPT_TEMPLATE_CACHE_PREFIX}{engine_id}" 