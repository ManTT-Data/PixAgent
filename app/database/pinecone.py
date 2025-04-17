import os
from pinecone import Pinecone
from dotenv import load_dotenv
import logging
from typing import Optional, List, Dict, Any
import time
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import google.generativeai as genai
from app.utils.utils import cache

# Cấu hình logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Pinecone API key and index name
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Configure Google API
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# Khởi tạo biến global để lưu trữ instance của Pinecone và index
pc = None
index = None
_retriever_instance = None

# Kiểm tra biến môi trường
if not PINECONE_API_KEY:
    logger.error("PINECONE_API_KEY is not set in environment variables")

if not PINECONE_INDEX_NAME:
    logger.error("PINECONE_INDEX_NAME is not set in environment variables")

# Initialize Pinecone
def init_pinecone():
    """Initialize pinecone connection using new API"""
    global pc, index
    
    try:
        # Chỉ khởi tạo nếu chưa khởi tạo trước đó
        if pc is None:
            logger.info(f"Initializing Pinecone connection to index {PINECONE_INDEX_NAME}...")
            
            # Khởi tạo client Pinecone theo API mới
            pc = Pinecone(api_key=PINECONE_API_KEY)
            
            # Kiểm tra xem index có tồn tại không
            index_list = pc.list_indexes()
            
            if not hasattr(index_list, 'names') or PINECONE_INDEX_NAME not in index_list.names():
                logger.error(f"Index {PINECONE_INDEX_NAME} does not exist in Pinecone")
                return None
            
            # Lấy index đã có
            index = pc.Index(PINECONE_INDEX_NAME)
            logger.info(f"Pinecone connection established to index {PINECONE_INDEX_NAME}")
            
        return index
    except Exception as e:
        logger.error(f"Error initializing Pinecone: {e}")
        return None

# Get Pinecone index singleton
def get_pinecone_index():
    """Get Pinecone index"""
    global index
    if index is None:
        index = init_pinecone()
    return index

# Kiểm tra kết nối Pinecone
def check_db_connection():
    """Kiểm tra kết nối Pinecone"""
    try:
        pinecone_index = get_pinecone_index()
        if pinecone_index is None:
            return False
            
        # Kiểm tra thông tin index để xác nhận kết nối đang hoạt động
        stats = pinecone_index.describe_index_stats()
        
        # Lấy tổng số vector từ cấu trúc kết quả mới
        total_vectors = stats.get('total_vector_count', 0)
        if hasattr(stats, 'namespaces'):
            # Nếu có namespace, tính tổng số vector từ các namespace
            total_vectors = sum(ns.get('vector_count', 0) for ns in stats.namespaces.values())
            
        logger.info(f"Pinecone connection is working. Total vectors: {total_vectors}")
        return True
    except Exception as e:
        logger.error(f"Error in Pinecone connection: {e}")
        return False

# Search vectors in Pinecone
async def search_vectors(query_vector, top_k=3, namespace="", filter=None):
    """Search for most similar vectors in Pinecone"""
    try:
        # Tạo cache key từ các tham số
        vector_hash = hash(str(query_vector))
        cache_key = f"pinecone_search:{vector_hash}:{top_k}:{namespace}:{filter}"
        
        # Kiểm tra cache trước
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.info("Returning cached Pinecone search results")
            return cached_result
        
        # Nếu không có trong cache, thực hiện tìm kiếm
        pinecone_index = get_pinecone_index()
        if pinecone_index is None:
            logger.error("Failed to get Pinecone index for search")
            return None
            
        results = pinecone_index.query(
            vector=query_vector,
            top_k=top_k,
            namespace=namespace,
            filter=filter,
            include_metadata=True
        )
        
        # Log search result metrics
        match_count = len(results.matches) if hasattr(results, 'matches') else 0
        logger.info(f"Pinecone search returned {match_count} matches")
        
        # Lưu kết quả vào cache với thời gian sống 5 phút
        cache.set(cache_key, results, ttl=300)
        
        return results
    except Exception as e:
        logger.error(f"Error searching vectors: {e}")
        return None

# Upsert vectors to Pinecone
async def upsert_vectors(vectors, namespace=""):
    """Upsert vectors to Pinecone index"""
    try:
        pinecone_index = get_pinecone_index()
        if pinecone_index is None:
            logger.error("Failed to get Pinecone index for upsert")
            return None
            
        response = pinecone_index.upsert(
            vectors=vectors,
            namespace=namespace
        )
        
        # Log upsert metrics
        upserted_count = response.get('upserted_count', 0)
        logger.info(f"Upserted {upserted_count} vectors to Pinecone")
        
        return response
    except Exception as e:
        logger.error(f"Error upserting vectors: {e}")
        return None

# Xóa vector từ Pinecone
async def delete_vectors(ids, namespace=""):
    """Delete vectors from Pinecone index"""
    try:
        pinecone_index = get_pinecone_index()
        if pinecone_index is None:
            logger.error("Failed to get Pinecone index for delete")
            return False
            
        response = pinecone_index.delete(
            ids=ids,
            namespace=namespace
        )
        
        logger.info(f"Deleted vectors with IDs {ids} from Pinecone")
        return True
    except Exception as e:
        logger.error(f"Error deleting vectors: {e}")
        return False

# Fetch vector metadata from Pinecone
async def fetch_metadata(ids, namespace=""):
    """Fetch metadata for specific vector IDs"""
    try:
        pinecone_index = get_pinecone_index()
        if pinecone_index is None:
            logger.error("Failed to get Pinecone index for fetch")
            return None
            
        response = pinecone_index.fetch(
            ids=ids,
            namespace=namespace
        )
        
        return response
    except Exception as e:
        logger.error(f"Error fetching vector metadata: {e}")
        return None

# Functions imported from chatbot.py

def get_chain(index_name = PINECONE_INDEX_NAME, namespace = "Default"):
    """Get the retrieval chain with Pinecone vector store (singleton pattern)"""
    global _retriever_instance
    try:
        if _retriever_instance is not None:
            return _retriever_instance
        
        # Kiểm tra xem chain đã được cache chưa
        cached_retriever = cache.get("pinecone_retriever")
        if cached_retriever is not None:
            _retriever_instance = cached_retriever
            logger.info("Retrieved cached Pinecone retriever")
            return _retriever_instance
            
        start_time = time.time()
        # Initialize embeddings model
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        
        # Get index
        pinecone_index = get_pinecone_index()
        if not pinecone_index:
            logger.error("Failed to get Pinecone index for retriever chain")
            return None
            
        # Use the PineconeVectorStore from langchain
        from langchain_pinecone import PineconeVectorStore
        vectorstore = PineconeVectorStore.from_existing_index(
            index_name=index_name,
            embedding=embeddings,
            text_key="text",
            namespace=namespace
        )
        
        _retriever_instance = vectorstore.as_retriever(search_kwargs={"k": 6})
        logger.info(f"Pinecone retriever initialized in {time.time() - start_time:.2f} seconds")
        
        # Cache the retriever with longer TTL (1 hour) since it rarely changes
        cache.set("pinecone_retriever", _retriever_instance, ttl=3600)
        
        return _retriever_instance
    except Exception as e:
        logger.error(f"Error creating retrieval chain: {e}")
        return None