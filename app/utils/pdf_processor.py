import os
import time
import uuid
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import logging
from pinecone import Pinecone

from app.database.pinecone import get_pinecone_index, init_pinecone
from app.database.postgresql import get_db
from app.database.models import VectorDatabase

# Configure logging
logger = logging.getLogger(__name__)

# Initialize embeddings model
embeddings_model = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

class PDFProcessor:
    """Class for processing PDF files and creating embeddings"""
    
    def __init__(self, index_name="testbot768", namespace="Default", api_key=None, vector_db_id=None, mock_mode=False):
        """Initialize with Pinecone index name, namespace and API key"""
        self.index_name = index_name
        self.namespace = namespace
        self.pinecone_index = None
        self.api_key = api_key
        self.vector_db_id = vector_db_id
        self.pinecone_client = None
        self.mock_mode = mock_mode  # Add mock mode for testing
        
    def _get_api_key_from_db(self):
        """Get API key from database if not provided directly"""
        if self.api_key:
            return self.api_key
            
        if not self.vector_db_id:
            logger.error("No API key provided and no vector_db_id to fetch from database")
            return None
            
        try:
            # Get database session
            db = next(get_db())
            
            # Get vector database
            vector_db = db.query(VectorDatabase).filter(
                VectorDatabase.id == self.vector_db_id
            ).first()
            
            if not vector_db:
                logger.error(f"Vector database with ID {self.vector_db_id} not found")
                return None
                
            # Get API key from relationship
            if hasattr(vector_db, 'api_key_ref') and vector_db.api_key_ref and hasattr(vector_db.api_key_ref, 'key_value'):
                logger.info(f"Using API key from api_key table for vector database ID {self.vector_db_id}")
                return vector_db.api_key_ref.key_value
                
            logger.error(f"No API key found for vector database ID {self.vector_db_id}. Make sure the api_key_id is properly set.")
            return None
        except Exception as e:
            logger.error(f"Error fetching API key from database: {e}")
            return None
    
    def _init_pinecone_connection(self):
        """Initialize connection to Pinecone with new API"""
        try:
            # If in mock mode, return a mock index
            if self.mock_mode:
                logger.info("Running in mock mode - simulating Pinecone connection")
                class MockPineconeIndex:
                    def upsert(self, vectors, namespace=None):
                        logger.info(f"Mock upsert: {len(vectors)} vectors to namespace '{namespace}'")
                        return {"upserted_count": len(vectors)}
                        
                    def delete(self, ids=None, delete_all=False, namespace=None):
                        logger.info(f"Mock delete: {'all vectors' if delete_all else f'{len(ids)} vectors'} from namespace '{namespace}'")
                        return {"deleted_count": 10 if delete_all else len(ids or [])}
                        
                    def describe_index_stats(self):
                        logger.info(f"Mock describe_index_stats")
                        return {"total_vector_count": 100, "namespaces": {self.namespace: {"vector_count": 50}}}
                
                return MockPineconeIndex()
            
            # Get API key from database if not provided
            api_key = self._get_api_key_from_db()
            
            if not api_key or not self.index_name:
                logger.error("Pinecone API key or index name not available")
                return None
            
            # Initialize Pinecone client using the new API
            self.pinecone_client = Pinecone(api_key=api_key)
            
            # Get the index
            index_list = self.pinecone_client.list_indexes()
            existing_indexes = index_list.names() if hasattr(index_list, 'names') else []
            
            if self.index_name not in existing_indexes:
                logger.error(f"Index {self.index_name} does not exist in Pinecone")
                return None
            
            # Connect to the index
            index = self.pinecone_client.Index(self.index_name)
            logger.info(f"Connected to Pinecone index: {self.index_name}")
            return index
        except Exception as e:
            logger.error(f"Error connecting to Pinecone: {e}")
            return None
            
    async def process_pdf(self, file_path, document_id=None, metadata=None, progress_callback=None):
        """
        Process PDF file, split into chunks and create embeddings
        
        Args:
            file_path (str): Path to the PDF file
            document_id (str, optional): Document ID, if not provided a new ID will be created
            metadata (dict, optional): Additional metadata for the document
            progress_callback (callable, optional): Callback function for progress updates
            
        Returns:
            dict: Processing result information including document_id and processed chunks count
        """
        try:
            # Initialize Pinecone connection if not already done
            self.pinecone_index = self._init_pinecone_connection()
            if not self.pinecone_index:
                return {"success": False, "error": "Could not connect to Pinecone"}
            
            # Create document_id if not provided
            if not document_id:
                document_id = str(uuid.uuid4())
            
            # Load PDF using PyPDFLoader
            logger.info(f"Reading PDF file: {file_path}")
            if progress_callback:
                await progress_callback("pdf_loading", 0.5, "Loading PDF file")
                
            loader = PyPDFLoader(file_path)
            pages = loader.load()
            
            # Extract and concatenate text from all pages
            all_text = ""
            for page in pages:
                all_text += page.page_content + "\n"
            
            if progress_callback:
                await progress_callback("text_extraction", 0.6, "Extracted text from PDF")
                
            # Split text into chunks
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=300)
            chunks = text_splitter.split_text(all_text)
            
            logger.info(f"Split PDF file into {len(chunks)} chunks")
            if progress_callback:
                await progress_callback("chunking", 0.7, f"Split document into {len(chunks)} chunks")
            
            # Process embeddings for each chunk and upsert to Pinecone
            vectors = []
            for i, chunk in enumerate(chunks):
                # Update embedding progress
                if progress_callback and i % 5 == 0:  # Update every 5 chunks to avoid too many notifications
                    embedding_progress = 0.7 + (0.3 * (i / len(chunks)))
                    await progress_callback("embedding", embedding_progress, f"Processing chunk {i+1}/{len(chunks)}")
                
                # Create vector embedding for each chunk
                vector = embeddings_model.embed_query(chunk)
                
                # Prepare metadata for vector
                vector_metadata = {
                    "document_id": document_id,
                    "chunk_index": i,
                    "text": chunk
                }
                
                # Add additional metadata if provided
                if metadata:
                    for key, value in metadata.items():
                        if key not in vector_metadata:
                            vector_metadata[key] = value
                
                # Add vector to list for upserting
                vectors.append({
                    "id": f"{document_id}_{i}",
                    "values": vector,
                    "metadata": vector_metadata
                })
                
                # Upsert in batches of 100 to avoid overloading
                if len(vectors) >= 100:
                    await self._upsert_vectors(vectors)
                    vectors = []
            
            # Upsert any remaining vectors
            if vectors:
                await self._upsert_vectors(vectors)
            
            logger.info(f"Embedded and saved {len(chunks)} chunks from PDF with document_id: {document_id}")
            
            # Final progress update
            if progress_callback:
                await progress_callback("completed", 1.0, "PDF processing complete")
            
            return {
                "success": True,
                "document_id": document_id,
                "chunks_processed": len(chunks),
                "total_text_length": len(all_text)
            }
            
        except Exception as e:
            logger.error(f"Error processing PDF: {str(e)}")
            if progress_callback:
                await progress_callback("error", 0, f"Error processing PDF: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _upsert_vectors(self, vectors):
        """Upsert vectors to Pinecone"""
        try:
            if not vectors:
                return
                
            # Ensure we have a valid pinecone_index
            if not self.pinecone_index:
                self.pinecone_index = self._init_pinecone_connection()
                if not self.pinecone_index:
                    raise Exception("Cannot connect to Pinecone")
            
            result = self.pinecone_index.upsert(
                vectors=vectors,
                namespace=self.namespace
            )
            
            logger.info(f"Upserted {len(vectors)} vectors to Pinecone")
            return result
        except Exception as e:
            logger.error(f"Error upserting vectors: {str(e)}")
            raise
    
    async def delete_namespace(self):
        """
        Delete all vectors in the current namespace (equivalent to deleting the namespace).
        """
        # Initialize connection if needed
        self.pinecone_index = self._init_pinecone_connection()
        if not self.pinecone_index:
            return {"success": False, "error": "Could not connect to Pinecone"}

        try:
            # delete_all=True will delete all vectors in the namespace
            result = self.pinecone_index.delete(
                delete_all=True,
                namespace=self.namespace
            )
            logger.info(f"Deleted namespace '{self.namespace}' (all vectors).")
            return {"success": True, "detail": result}
        except Exception as e:
            logger.error(f"Error deleting namespace '{self.namespace}': {e}")
            return {"success": False, "error": str(e)}
    
    async def list_documents(self):
        """Get list of all document_ids from Pinecone"""
        try:
            # Initialize Pinecone connection if not already done
            self.pinecone_index = self._init_pinecone_connection()
            if not self.pinecone_index:
                return {"success": False, "error": "Could not connect to Pinecone"}
            
            # Get index information
            stats = self.pinecone_index.describe_index_stats()
            
            # Query to get list of all unique document_ids
            # This method may not be efficient with large datasets, but is the simplest approach
            # In practice, you should maintain a list of document_ids in a separate database
            
            return {
                "success": True,
                "total_vectors": stats.get('total_vector_count', 0),
                "namespace": self.namespace,
                "index_name": self.index_name
            }
        except Exception as e:
            logger.error(f"Error getting document list: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            } 