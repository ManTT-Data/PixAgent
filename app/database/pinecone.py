import os
from pinecone import Pinecone
from dotenv import load_dotenv
import logging
from typing import Optional, List, Dict, Any, Union, Tuple
import time
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import google.generativeai as genai
from app.utils.utils import cache
from langchain_core.retrievers import BaseRetriever
from langchain.callbacks.manager import Callbacks
from langchain_core.documents import Document
from langchain_core.pydantic_v1 import Field

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Pinecone API key and index name
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Pinecone retrieval configuration
DEFAULT_LIMIT_K = int(os.getenv("PINECONE_DEFAULT_LIMIT_K", "10"))
DEFAULT_TOP_K = int(os.getenv("PINECONE_DEFAULT_TOP_K", "6"))
DEFAULT_SIMILARITY_METRIC = os.getenv("PINECONE_DEFAULT_SIMILARITY_METRIC", "cosine")
DEFAULT_SIMILARITY_THRESHOLD = float(os.getenv("PINECONE_DEFAULT_SIMILARITY_THRESHOLD", "0.75"))
ALLOWED_METRICS = os.getenv("PINECONE_ALLOWED_METRICS", "cosine,dotproduct,euclidean").split(",")

# Export constants for importing elsewhere
__all__ = [
    'get_pinecone_index', 
    'check_db_connection', 
    'search_vectors', 
    'upsert_vectors', 
    'delete_vectors', 
    'fetch_metadata',
    'get_chain',
    'DEFAULT_TOP_K',
    'DEFAULT_LIMIT_K',
    'DEFAULT_SIMILARITY_METRIC',
    'DEFAULT_SIMILARITY_THRESHOLD',
    'ALLOWED_METRICS',
    'ThresholdRetriever'
]

# Configure Google API
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# Initialize global variables to store instances of Pinecone and index
pc = None
index = None
_retriever_instance = None

# Check environment variables
if not PINECONE_API_KEY:
    logger.error("PINECONE_API_KEY is not set in environment variables")

if not PINECONE_INDEX_NAME:
    logger.error("PINECONE_INDEX_NAME is not set in environment variables")

# Initialize Pinecone
def init_pinecone():
    """Initialize pinecone connection using new API"""
    global pc, index
    
    try:
        # Only initialize if not already initialized
        if pc is None:
            logger.info(f"Initializing Pinecone connection to index {PINECONE_INDEX_NAME}...")
            
            # Check if API key and index name are set
            if not PINECONE_API_KEY:
                logger.error("PINECONE_API_KEY is not set in environment variables")
                return None
                
            if not PINECONE_INDEX_NAME:
                logger.error("PINECONE_INDEX_NAME is not set in environment variables")
                return None
            
            # Initialize Pinecone client using the new API
            pc = Pinecone(api_key=PINECONE_API_KEY)
            
            try:
                # Check if index exists
                index_list = pc.list_indexes()
                
                if not hasattr(index_list, 'names') or PINECONE_INDEX_NAME not in index_list.names():
                    logger.error(f"Index {PINECONE_INDEX_NAME} does not exist in Pinecone")
                    return None
                
                # Get existing index
                index = pc.Index(PINECONE_INDEX_NAME)
                logger.info(f"Pinecone connection established to index {PINECONE_INDEX_NAME}")
            except Exception as connection_error:
                logger.error(f"Error connecting to Pinecone index: {connection_error}")
                return None
            
        return index
    except ImportError as e:
        logger.error(f"Required package for Pinecone is missing: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error initializing Pinecone: {e}")
        return None

# Get Pinecone index singleton
def get_pinecone_index():
    """Get Pinecone index"""
    global index
    if index is None:
        index = init_pinecone()
    return index

# Check Pinecone connection
def check_db_connection():
    """Check Pinecone connection"""
    try:
        pinecone_index = get_pinecone_index()
        if pinecone_index is None:
            return False
            
        # Check index information to confirm connection is working
        stats = pinecone_index.describe_index_stats()
        
        # Get total vector count from the new result structure
        total_vectors = stats.get('total_vector_count', 0)
        if hasattr(stats, 'namespaces'):
            # If there are namespaces, calculate total vector count from namespaces
            total_vectors = sum(ns.get('vector_count', 0) for ns in stats.namespaces.values())
            
        logger.info(f"Pinecone connection is working. Total vectors: {total_vectors}")
        return True
    except Exception as e:
        logger.error(f"Error in Pinecone connection: {e}")
        return False

# Convert similarity score based on the metric
def convert_score(score: float, metric: str) -> float:
    """
    Convert similarity score to a 0-1 scale based on the metric used.
    For metrics like euclidean distance where lower is better, we invert the score.
    
    Args:
        score: The raw similarity score
        metric: The similarity metric used
        
    Returns:
        A normalized score between 0-1 where higher means more similar
    """
    if metric.lower() in ["euclidean", "l2"]:
        # For distance metrics (lower is better), we inverse and normalize
        # Assuming max reasonable distance is 2.0 for normalized vectors
        return max(0, 1 - (score / 2.0))
    else:
        # For cosine and dot product (higher is better), return as is
        return score

# Filter results based on similarity threshold
def filter_by_threshold(results, threshold: float, metric: str) -> List[Dict]:
    """
    Filter query results based on similarity threshold.
    
    Args:
        results: The query results from Pinecone
        threshold: The similarity threshold (0-1)
        metric: The similarity metric used
        
    Returns:
        Filtered list of matches
    """
    filtered_matches = []
    
    if not hasattr(results, 'matches'):
        return filtered_matches
        
    for match in results.matches:
        # Get the score
        score = getattr(match, 'score', 0)
        
        # Convert score based on metric
        normalized_score = convert_score(score, metric)
        
        # Filter based on threshold
        if normalized_score >= threshold:
            # Add normalized score as an additional attribute
            match.normalized_score = normalized_score
            filtered_matches.append(match)
    
    return filtered_matches

# Search vectors in Pinecone with advanced options
async def search_vectors(
    query_vector, 
    top_k: int = DEFAULT_TOP_K,
    limit_k: int = DEFAULT_LIMIT_K,
    similarity_metric: str = DEFAULT_SIMILARITY_METRIC,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    namespace: str = "", 
    filter: Optional[Dict] = None
) -> Dict:
    """
    Search for most similar vectors in Pinecone with advanced filtering options.
    
    Args:
        query_vector: The query vector
        top_k: Number of results to return (after threshold filtering)
        limit_k: Maximum number of results to retrieve from Pinecone
        similarity_metric: Similarity metric to use (cosine, dotproduct, euclidean)
        similarity_threshold: Threshold for similarity (0-1)
        namespace: Namespace to search in
        filter: Filter query
        
    Returns:
        Search results with matches filtered by threshold
    """
    try:
        # Validate parameters
        if similarity_metric not in ALLOWED_METRICS:
            logger.warning(f"Invalid similarity metric: {similarity_metric}. Using default: {DEFAULT_SIMILARITY_METRIC}")
            similarity_metric = DEFAULT_SIMILARITY_METRIC
            
        if limit_k < top_k:
            logger.warning(f"limit_k ({limit_k}) must be greater than or equal to top_k ({top_k}). Setting limit_k to {top_k}")
            limit_k = top_k
            
        # Create cache key from parameters
        vector_hash = hash(str(query_vector))
        cache_key = f"pinecone_search:{vector_hash}:{limit_k}:{similarity_metric}:{similarity_threshold}:{namespace}:{filter}"
        
        # Check cache first
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.info("Returning cached Pinecone search results")
            return cached_result
        
        # If not in cache, perform search
        pinecone_index = get_pinecone_index()
        if pinecone_index is None:
            logger.error("Failed to get Pinecone index for search")
            return None
            
        # Query Pinecone with the provided metric and higher limit_k to allow for threshold filtering
        results = pinecone_index.query(
            vector=query_vector,
            top_k=limit_k,  # Retrieve more results than needed to allow for threshold filtering
            namespace=namespace,
            filter=filter,
            include_metadata=True,
            include_values=False,  # No need to return vector values to save bandwidth
            metric=similarity_metric  # Specify similarity metric
        )
        
        # Filter results by threshold
        filtered_matches = filter_by_threshold(results, similarity_threshold, similarity_metric)
        
        # Limit to top_k after filtering
        filtered_matches = filtered_matches[:top_k]
        
        # Create a new results object with filtered matches
        results.matches = filtered_matches
        
        # Log search result metrics
        match_count = len(filtered_matches)
        logger.info(f"Pinecone search returned {match_count} matches after threshold filtering (metric: {similarity_metric}, threshold: {similarity_threshold})")
        
        # Store result in cache with 5 minute TTL
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

# Delete vectors from Pinecone
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

# Create a custom retriever class for Langchain integration
class ThresholdRetriever(BaseRetriever):
    """
    Custom retriever that supports threshold-based filtering and multiple similarity metrics.
    This integrates with the Langchain ecosystem while using our advanced retrieval logic.
    """
    
    vectorstore: Any = Field(description="Vector store to use for retrieval")
    embeddings: Any = Field(description="Embeddings model to use for retrieval")
    search_kwargs: Dict[str, Any] = Field(default_factory=dict, description="Search kwargs for the vectorstore")
    top_k: int = Field(default=DEFAULT_TOP_K, description="Number of results to return after filtering")
    limit_k: int = Field(default=DEFAULT_LIMIT_K, description="Maximum number of results to retrieve from Pinecone")
    similarity_metric: str = Field(default=DEFAULT_SIMILARITY_METRIC, description="Similarity metric to use")
    similarity_threshold: float = Field(default=DEFAULT_SIMILARITY_THRESHOLD, description="Threshold for similarity")
    
    class Config:
        """Configuration for this pydantic object."""
        arbitrary_types_allowed = True
    
    async def search_vectors_sync(
        self, query_vector, 
        top_k: int = DEFAULT_TOP_K,
        limit_k: int = DEFAULT_LIMIT_K,
        similarity_metric: str = DEFAULT_SIMILARITY_METRIC,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        namespace: str = "", 
        filter: Optional[Dict] = None
    ) -> Dict:
        """Synchronous wrapper for search_vectors"""
        import asyncio
        try:
            # Get current event loop or create a new one
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Use event loop to run async function
            if loop.is_running():
                # If we're in an event loop, use asyncio.create_task
                task = asyncio.create_task(search_vectors(
                    query_vector=query_vector,
                    top_k=top_k,
                    limit_k=limit_k,
                    similarity_metric=similarity_metric,
                    similarity_threshold=similarity_threshold,
                    namespace=namespace,
                    filter=filter
                ))
                return await task
            else:
                # If not in an event loop, just await directly
                return await search_vectors(
                    query_vector=query_vector,
                    top_k=top_k,
                    limit_k=limit_k,
                    similarity_metric=similarity_metric,
                    similarity_threshold=similarity_threshold,
                    namespace=namespace,
                    filter=filter
                )
        except Exception as e:
            logger.error(f"Error in search_vectors_sync: {e}")
            return None

    def _get_relevant_documents(
        self, query: str, *, run_manager: Callbacks = None
    ) -> List[Document]:
        """
        Get documents relevant to the query using threshold-based retrieval.
        
        Args:
            query: The query string
            run_manager: The callbacks manager
            
        Returns:
            List of relevant documents
        """
        # Generate embedding for query using the embeddings model
        try:
            # Use the embeddings model we stored in the class
            embedding = self.embeddings.embed_query(query)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            # Fallback to creating a new embedding model if needed
            embedding_model = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
            embedding = embedding_model.embed_query(query)
        
        # Perform search with advanced options - avoid asyncio.run()
        import asyncio
        
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        # Run asynchronous search in a safe way
        if loop.is_running():
            # We're inside an existing event loop (like in FastAPI)
            # Use a different approach - convert it to a synchronous call
            from concurrent.futures import ThreadPoolExecutor
            import functools
            
            # Define a wrapper function to run in a thread
            def run_async_in_thread():
                # Create a new event loop for this thread
                thread_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(thread_loop)
                # Run the coroutine and return the result
                return thread_loop.run_until_complete(search_vectors(
                    query_vector=embedding,
                    top_k=self.top_k,
                    limit_k=self.limit_k,
                    similarity_metric=self.similarity_metric,
                    similarity_threshold=self.similarity_threshold,
                    namespace=getattr(self.vectorstore, "namespace", ""),
                    filter=self.search_kwargs.get("filter", None)
                ))
            
            # Run the async function in a thread
            with ThreadPoolExecutor() as executor:
                search_result = executor.submit(run_async_in_thread).result()
        else:
            # No event loop running, we can use run_until_complete
            search_result = loop.run_until_complete(search_vectors(
                query_vector=embedding,
                top_k=self.top_k,
                limit_k=self.limit_k,
                similarity_metric=self.similarity_metric,
                similarity_threshold=self.similarity_threshold,
                namespace=getattr(self.vectorstore, "namespace", ""),
                filter=self.search_kwargs.get("filter", None)
            ))
        
        # Convert to documents
        documents = []
        if search_result and hasattr(search_result, 'matches'):
            for match in search_result.matches:
                # Extract metadata
                metadata = {}
                if hasattr(match, 'metadata'):
                    metadata = match.metadata
                
                # Add score to metadata
                score = getattr(match, 'score', 0)
                normalized_score = getattr(match, 'normalized_score', score)
                metadata['score'] = score
                metadata['normalized_score'] = normalized_score
                
                # Extract text
                text = metadata.get('text', '')
                if 'text' in metadata:
                    del metadata['text']  # Remove from metadata since it's the content
                
                # Create Document
                doc = Document(
                    page_content=text,
                    metadata=metadata
                )
                documents.append(doc)
        
        return documents

# Get the retrieval chain with Pinecone vector store
def get_chain(
    index_name=PINECONE_INDEX_NAME, 
    namespace="Default", 
    top_k=DEFAULT_TOP_K, 
    limit_k=DEFAULT_LIMIT_K,
    similarity_metric=DEFAULT_SIMILARITY_METRIC, 
    similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD
):
    """
    Get the retrieval chain with Pinecone vector store using threshold-based retrieval.
    
    Args:
        index_name: Pinecone index name
        namespace: Pinecone namespace
        top_k: Number of results to return after filtering
        limit_k: Maximum number of results to retrieve from Pinecone
        similarity_metric: Similarity metric to use (cosine, dotproduct, euclidean)
        similarity_threshold: Threshold for similarity (0-1)
        
    Returns:
        ThresholdRetriever instance
    """
    global _retriever_instance
    try:
        # If already initialized with same parameters, return cached instance
        if _retriever_instance is not None:
            return _retriever_instance
            
        # Check if chain has been cached
        cache_key = f"pinecone_retriever:{index_name}:{namespace}:{top_k}:{limit_k}:{similarity_metric}:{similarity_threshold}"
        cached_retriever = cache.get(cache_key)
        if cached_retriever is not None:
            _retriever_instance = cached_retriever
            logger.info("Retrieved cached Pinecone retriever")
            return _retriever_instance
            
        start_time = time.time()
        logger.info("Initializing new retriever chain with threshold-based filtering")
        
        # Initialize embeddings model
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        
        # Get index
        pinecone_index = get_pinecone_index()
        if not pinecone_index:
            logger.error("Failed to get Pinecone index for retriever chain")
            return None
            
        # Get statistics for logging
        try:
            stats = pinecone_index.describe_index_stats()
            total_vectors = stats.get('total_vector_count', 0)
            logger.info(f"Pinecone index stats - Total vectors: {total_vectors}")
        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
        
        # Use Pinecone from langchain_community.vectorstores
        from langchain_community.vectorstores import Pinecone as LangchainPinecone
        
        logger.info(f"Creating Pinecone vectorstore with index: {index_name}, namespace: {namespace}")
        vectorstore = LangchainPinecone.from_existing_index(
            embedding=embeddings,
            index_name=index_name,
            namespace=namespace,
            text_key="text" 
        )
        
        # Create threshold-based retriever
        logger.info(f"Creating ThresholdRetriever with top_k={top_k}, limit_k={limit_k}, " +
                    f"metric={similarity_metric}, threshold={similarity_threshold}")
        
        # Create ThresholdRetriever with both vectorstore and embeddings
        _retriever_instance = ThresholdRetriever(
            vectorstore=vectorstore,
            embeddings=embeddings,  # Pass embeddings separately
            top_k=top_k,
            limit_k=limit_k,
            similarity_metric=similarity_metric,
            similarity_threshold=similarity_threshold
        )
        
        logger.info(f"Pinecone retriever initialized in {time.time() - start_time:.2f} seconds")
        
        # Cache the retriever with longer TTL (1 hour) since it rarely changes
        cache.set(cache_key, _retriever_instance, ttl=3600)
        
        return _retriever_instance
    except Exception as e:
        logger.error(f"Error creating retrieval chain: {e}")
        return None