"""
Improved Pinecone connection handling with dimension validation.
This module provides more robust connection and error handling for Pinecone operations.
"""
import logging
import time
from typing import Optional, Dict, Any, Tuple, List
import pinecone
from pinecone import Pinecone, ServerlessSpec, PodSpec

logger = logging.getLogger(__name__)

# Default retry settings
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2

class PineconeConnectionManager:
    """
    Manages Pinecone connections with enhanced error handling and dimension validation.
    
    This class centralizes Pinecone connection logic, providing:
    - Connection pooling/reuse
    - Automatic retries with exponential backoff
    - Dimension validation before operations
    - Detailed error logging for better debugging
    """
    
    # Class-level cache of Pinecone clients
    _clients = {}
    
    @classmethod
    def get_client(cls, api_key: str) -> Pinecone:
        """
        Returns a Pinecone client for the given API key, creating one if needed.
        
        Args:
            api_key: Pinecone API key
            
        Returns:
            Initialized Pinecone client
        """
        if not api_key:
            raise ValueError("Pinecone API key cannot be empty")
            
        # Return cached client if it exists
        if api_key in cls._clients:
            return cls._clients[api_key]
            
        # Log client creation (but hide full API key)
        key_prefix = api_key[:4] + "..." if len(api_key) > 4 else "invalid"
        logger.info(f"Creating new Pinecone client with API key (first 4 chars: {key_prefix}...)")
        
        try:
            # Initialize Pinecone client
            client = Pinecone(api_key=api_key)
            cls._clients[api_key] = client
            logger.info("Pinecone client created successfully")
            return client
        except Exception as e:
            logger.error(f"Failed to create Pinecone client: {str(e)}")
            raise RuntimeError(f"Pinecone client initialization failed: {str(e)}") from e
    
    @classmethod
    def get_index(cls, 
                  api_key: str, 
                  index_name: str, 
                  max_retries: int = DEFAULT_MAX_RETRIES) -> Any:
        """
        Get a Pinecone index with retry logic.
        
        Args:
            api_key: Pinecone API key
            index_name: Name of the index to connect to
            max_retries: Maximum number of retry attempts
            
        Returns:
            Pinecone index
        """
        client = cls.get_client(api_key)
        
        # Retry logic for connection issues
        for attempt in range(max_retries):
            try:
                index = client.Index(index_name)
                # Test the connection
                _ = index.describe_index_stats()
                logger.info(f"Connected to Pinecone index: {index_name}")
                return index
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = DEFAULT_RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Pinecone connection attempt {attempt+1} failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect to Pinecone index after {max_retries} attempts: {e}")
                    raise RuntimeError(f"Pinecone index connection failed: {str(e)}") from e
    
    @classmethod
    def validate_dimensions(cls, 
                            index: Any, 
                            vector_dimensions: int) -> Tuple[bool, Optional[str]]:
        """
        Validate that the vector dimensions match the Pinecone index configuration.
        
        Args:
            index: Pinecone index
            vector_dimensions: Dimensions of the vectors to be uploaded
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Get index stats
            stats = index.describe_index_stats()
            index_dimensions = stats.dimension
            
            if index_dimensions != vector_dimensions:
                error_msg = (f"Vector dimensions mismatch: Your vectors have {vector_dimensions} dimensions, "
                            f"but Pinecone index expects {index_dimensions} dimensions")
                logger.error(error_msg)
                return False, error_msg
                
            return True, None
        except Exception as e:
            error_msg = f"Failed to validate dimensions: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    @classmethod
    def upsert_vectors_with_validation(cls,
                                    index: Any,
                                    vectors: List[Dict[str, Any]],
                                    namespace: str = "",
                                    batch_size: int = 100) -> Dict[str, Any]:
        """
        Upsert vectors with dimension validation and batching.
        
        Args:
            index: Pinecone index
            vectors: List of vectors to upsert, each with 'id', 'values', and optional 'metadata'
            namespace: Namespace to upsert to
            batch_size: Size of batches for upserting
            
        Returns:
            Result of upsert operation
        """
        if not vectors:
            return {"upserted_count": 0, "success": True}
            
        # Validate dimensions with the first vector
        if "values" in vectors[0] and len(vectors[0]["values"]) > 0:
            vector_dim = len(vectors[0]["values"])
            is_valid, error_msg = cls.validate_dimensions(index, vector_dim)
            
            if not is_valid:
                logger.error(f"Dimension validation failed: {error_msg}")
                raise ValueError(f"Vector dimensions do not match Pinecone index configuration: {error_msg}")
        
        # Batch upsert
        total_upserted = 0
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i+batch_size]
            try:
                result = index.upsert(vectors=batch, namespace=namespace)
                batch_upserted = result.get("upserted_count", len(batch))
                total_upserted += batch_upserted
                logger.info(f"Upserted batch {i//batch_size + 1}: {batch_upserted} vectors")
            except Exception as e:
                logger.error(f"Failed to upsert batch {i//batch_size + 1}: {str(e)}")
                raise RuntimeError(f"Vector upsert failed: {str(e)}") from e
                
        return {"upserted_count": total_upserted, "success": True}

# Simplified function to check connection
def check_connection(api_key: str, index_name: str) -> bool:
    """
    Test Pinecone connection and validate index exists.
    
    Args:
        api_key: Pinecone API key
        index_name: Name of index to test
        
    Returns:
        True if connection successful, False otherwise
    """
    try:
        index = PineconeConnectionManager.get_index(api_key, index_name)
        stats = index.describe_index_stats()
        total_vectors = stats.total_vector_count
        logger.info(f"Pinecone connection is working. Total vectors: {total_vectors}")
        return True
    except Exception as e:
        logger.error(f"Pinecone connection failed: {str(e)}")
        return False 