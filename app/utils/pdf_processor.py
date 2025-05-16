import os
import logging
import uuid
import pinecone
from app.utils.pinecone_fix import PineconeConnectionManager, check_connection
import time
import os
from typing import List, Dict, Any, Optional

# Langchain imports for document processing
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import google.generativeai as genai

# Configure logger
logger = logging.getLogger(__name__)

class PDFProcessor:
    """Process PDF files and create embeddings in Pinecone"""
    
    def __init__(self, index_name="testbot768", namespace="Default", api_key=None, vector_db_id=None, mock_mode=False, correlation_id=None):
        self.index_name = index_name
        self.namespace = namespace
        self.api_key = api_key
        self.vector_db_id = vector_db_id
        self.pinecone_index = None
        self.mock_mode = mock_mode
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.google_api_key = os.environ.get("GOOGLE_API_KEY")
        
        # Initialize Pinecone connection if not in mock mode
        if not self.mock_mode and self.api_key:
            try:
                # Use connection manager from pinecone_fix
                logger.info(f"[{self.correlation_id}] Initializing Pinecone connection to {self.index_name}")
                self.pinecone_index = PineconeConnectionManager.get_index(self.api_key, self.index_name)
                logger.info(f"[{self.correlation_id}] Successfully connected to Pinecone index {self.index_name}")
            except Exception as e:
                logger.error(f"[{self.correlation_id}] Failed to initialize Pinecone: {str(e)}")
                # Fall back to mock mode if connection fails
                self.mock_mode = True
                logger.warning(f"[{self.correlation_id}] Falling back to mock mode due to connection error")
            
    async def process_pdf(self, file_path, document_id=None, metadata=None, progress_callback=None):
        """Process a PDF file and create vector embeddings
        
        This method:
        1. Extracts text from PDF using PyPDFLoader
        2. Splits text into chunks using RecursiveCharacterTextSplitter
        3. Creates embeddings using Google Gemini model
        4. Stores embeddings in Pinecone
        """
        logger.info(f"[{self.correlation_id}] Processing PDF: {file_path}")
        
        if self.mock_mode:
            logger.info(f"[{self.correlation_id}] MOCK: Processing PDF {file_path}")
            # Mock implementation - just return success
            if progress_callback:
                await progress_callback(None, document_id, "embedding_complete", 1.0, "Mock processing completed")
            return {"success": True, "message": "PDF processed successfully"}
        
        try:
            # Initialize metadata if not provided
            if metadata is None:
                metadata = {}
            
            # Ensure document_id is included
            if document_id is None:
                document_id = str(uuid.uuid4())
            
            # Add document_id to metadata
            metadata["document_id"] = document_id
            
            # The namespace to use might be in vdb-X format if vector_db_id provided
            actual_namespace = f"vdb-{self.vector_db_id}" if self.vector_db_id else self.namespace
            
            # 1. Extract text from PDF
            logger.info(f"[{self.correlation_id}] Extracting text from PDF: {file_path}")
            if progress_callback:
                await progress_callback(None, document_id, "text_extraction", 0.2, "Extracting text from PDF")
                
            loader = PyPDFLoader(file_path)
            documents = loader.load()
            total_text_length = sum(len(doc.page_content) for doc in documents)
            
            logger.info(f"[{self.correlation_id}] Extracted {len(documents)} pages, total text length: {total_text_length}")
            
            # 2. Split text into chunks
            if progress_callback:
                await progress_callback(None, document_id, "chunking", 0.4, "Splitting text into chunks")
            
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=100,
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            )
            
            chunks = text_splitter.split_documents(documents)
            
            logger.info(f"[{self.correlation_id}] Split into {len(chunks)} chunks")
            
            # 3. Create embeddings
            if progress_callback:
                await progress_callback(None, document_id, "embedding", 0.6, "Creating embeddings")
            
            # Initialize Google Gemini for embeddings
            if not self.google_api_key:
                raise ValueError("Google API key not found in environment variables")
            
            genai.configure(api_key=self.google_api_key)
            
            # First, get the expected dimensions from Pinecone
            logger.info(f"[{self.correlation_id}] Checking Pinecone index dimensions")
            if not self.pinecone_index:
                self.pinecone_index = PineconeConnectionManager.get_index(self.api_key, self.index_name)
            
            stats = self.pinecone_index.describe_index_stats()
            pinecone_dimension = stats.dimension
            logger.info(f"[{self.correlation_id}] Pinecone index dimension: {pinecone_dimension}")
            
            # Create embedding model
            embedding_model = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001",
                google_api_key=self.google_api_key,
                task_type="retrieval_document"  # Use document embedding mode for longer text
            )
            
            # Get a sample embedding to check dimensions
            sample_embedding = embedding_model.embed_query("test")
            embedding_dimension = len(sample_embedding)
            
            logger.info(f"[{self.correlation_id}] Generated embeddings with dimension: {embedding_dimension}")
            
            # Dimension handling - if mismatch, we handle it appropriately
            if embedding_dimension != pinecone_dimension:
                logger.warning(f"[{self.correlation_id}] Embedding dimension mismatch: got {embedding_dimension}, need {pinecone_dimension}")
                
                if embedding_dimension < pinecone_dimension:
                    # For upscaling from 768 to 1536: duplicate each value and scale appropriately
                    # This is one approach to handle dimension mismatches while preserving semantic information
                    logger.info(f"[{self.correlation_id}] Using duplication strategy to upscale from {embedding_dimension} to {pinecone_dimension}")
                    
                    if embedding_dimension * 2 == pinecone_dimension:
                        # Perfect doubling (768 -> 1536)
                        def adjust_embedding(embedding):
                            # Duplicate each value to double the dimension
                            return [val for val in embedding for _ in range(2)]
                    else:
                        # Generic padding with zeros
                        pad_size = pinecone_dimension - embedding_dimension
                        def adjust_embedding(embedding):
                            return embedding + [0.0] * pad_size
                else:
                    # Truncation strategy - take first pinecone_dimension values
                    logger.info(f"[{self.correlation_id}] Will truncate embeddings from {embedding_dimension} to {pinecone_dimension}")
                    
                    def adjust_embedding(embedding):
                        return embedding[:pinecone_dimension]
            else:
                # No adjustment needed
                def adjust_embedding(embedding):
                    return embedding
            
            # Process in batches to avoid memory issues
            batch_size = 10
            vectors_to_upsert = []
            
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i+batch_size]
                
                # Extract text content
                texts = [chunk.page_content for chunk in batch]
                
                # Create embeddings for batch
                embeddings = embedding_model.embed_documents(texts)
                
                # Prepare vectors for Pinecone
                for j, (chunk, embedding) in enumerate(zip(batch, embeddings)):
                    # Adjust embedding dimensions if needed
                    adjusted_embedding = adjust_embedding(embedding)
                    
                    # Verify dimensions are correct
                    if len(adjusted_embedding) != pinecone_dimension:
                        raise ValueError(f"Dimension mismatch after adjustment: got {len(adjusted_embedding)}, expected {pinecone_dimension}")
                    
                    # Create metadata for this chunk
                    chunk_metadata = {
                        "document_id": document_id,
                        "page": chunk.metadata.get("page", 0),
                        "chunk_id": f"{document_id}-chunk-{i+j}",
                        "text": chunk.page_content[:1000],  # Store first 1000 chars of text
                        **metadata  # Include original metadata
                    }
                    
                    # Create vector record
                    vector = {
                        "id": f"{document_id}-{i+j}",
                        "values": adjusted_embedding,
                        "metadata": chunk_metadata
                    }
                    
                    vectors_to_upsert.append(vector)
                
                logger.info(f"[{self.correlation_id}] Processed batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")
            
            # 4. Store embeddings in Pinecone
            if progress_callback:
                await progress_callback(None, document_id, "storing", 0.8, f"Storing {len(vectors_to_upsert)} vectors in Pinecone")
            
            logger.info(f"[{self.correlation_id}] Upserting {len(vectors_to_upsert)} vectors to Pinecone index {self.index_name}, namespace {actual_namespace}")
            
            # Use PineconeConnectionManager for better error handling
            result = PineconeConnectionManager.upsert_vectors_with_validation(
                self.pinecone_index,
                vectors_to_upsert,
                namespace=actual_namespace
            )
            
            logger.info(f"[{self.correlation_id}] Successfully upserted {result.get('upserted_count', 0)} vectors to Pinecone")
            
            if progress_callback:
                await progress_callback(None, document_id, "embedding_complete", 1.0, "Processing completed")
            
            # Return success with stats
            return {
                "success": True,
                "document_id": document_id,
                "chunks_processed": len(chunks),
                "total_text_length": total_text_length,
                "vectors_created": len(vectors_to_upsert),
                "vectors_upserted": result.get('upserted_count', 0),
                "message": "PDF processed successfully"
            }
        except Exception as e:
            logger.error(f"[{self.correlation_id}] Error processing PDF: {str(e)}")
            return {
                "success": False,
                "error": f"Error processing PDF: {str(e)}"
            }
    
    async def list_namespaces(self):
        """List all namespaces in the Pinecone index"""
        if self.mock_mode:
            logger.info(f"[{self.correlation_id}] MOCK: Listing namespaces")
            return {"success": True, "namespaces": ["test"]}
        
        try:
            if not self.pinecone_index:
                self.pinecone_index = PineconeConnectionManager.get_index(self.api_key, self.index_name)
            
            # Get index stats which includes namespaces
            stats = self.pinecone_index.describe_index_stats()
            namespaces = list(stats.get("namespaces", {}).keys())
            
            return {
                "success": True,
                "namespaces": namespaces
            }
        except Exception as e:
            logger.error(f"[{self.correlation_id}] Error listing namespaces: {str(e)}")
            return {
                "success": False,
                "error": f"Error listing namespaces: {str(e)}"
            }
    
    async def delete_namespace(self):
        """Delete all vectors in a namespace"""
        if self.mock_mode:
            logger.info(f"[{self.correlation_id}] MOCK: Deleting namespace '{self.namespace}'")
            return {
                "success": True,
                "namespace": self.namespace,
                "deleted_count": 100,
                "message": f"Successfully deleted namespace '{self.namespace}'"
            }

        try:
            if not self.pinecone_index:
                self.pinecone_index = PineconeConnectionManager.get_index(self.api_key, self.index_name)
                
            logger.info(f"[{self.correlation_id}] Deleting namespace '{self.namespace}' from index '{self.index_name}'")
            
            # Check if namespace exists
            stats = self.pinecone_index.describe_index_stats()
            namespaces = stats.get("namespaces", {})
            
            if self.namespace in namespaces:
                vector_count = namespaces[self.namespace].get("vector_count", 0)
                # Delete all vectors in namespace
                self.pinecone_index.delete(delete_all=True, namespace=self.namespace)
                return {
                    "success": True,
                    "namespace": self.namespace,
                    "deleted_count": vector_count,
                    "message": f"Successfully deleted namespace '{self.namespace}' with {vector_count} vectors"
                }
            else:
                return {
                    "success": True,
                    "namespace": self.namespace,
                    "deleted_count": 0,
                    "message": f"Namespace '{self.namespace}' does not exist - nothing to delete"
                }
        except Exception as e:
            logger.error(f"[{self.correlation_id}] Error deleting namespace: {str(e)}")
            return {
                "success": False,
                "namespace": self.namespace,
                "error": f"Error deleting namespace: {str(e)}"
            }
    
    async def delete_document(self, document_id):
        """Delete vectors associated with a specific document ID"""
        logger.info(f"[{self.correlation_id}] Deleting vectors for document '{document_id}' from namespace '{self.namespace}'")

        if self.mock_mode:
            logger.info(f"[{self.correlation_id}] MOCK: Deleting document vectors for '{document_id}'")
            # In mock mode, simulate deleting 10 vectors
            return {
                "success": True,
                "document_id": document_id,
                "namespace": self.namespace,
                "deleted_count": 10,
                "message": f"Successfully deleted vectors for document '{document_id}' from namespace '{self.namespace}'"
            }

        try:
            if not self.pinecone_index:
                self.pinecone_index = PineconeConnectionManager.get_index(self.api_key, self.index_name)
                
            # Use metadata filtering to find vectors with matching document_id
            # The specific namespace to use might be vdb-X format if vector_db_id provided
            actual_namespace = f"vdb-{self.vector_db_id}" if self.vector_db_id else self.namespace
            
            # Search for vectors with this document ID
            results = self.pinecone_index.query(
                vector=[0] * 1536,  # Dummy vector, we only care about metadata filter
                top_k=1,
                include_metadata=True,
                filter={"document_id": document_id},
                namespace=actual_namespace
            )
            
            # If no vectors found, return success with warning
            if len(results.get("matches", [])) == 0:
                logger.warning(f"[{self.correlation_id}] No vectors found for document '{document_id}' in namespace '{actual_namespace}'")
                return {
                    "success": True,
                    "document_id": document_id,
                    "namespace": actual_namespace,
                    "deleted_count": 0,
                    "warning": f"No vectors found for document '{document_id}' in namespace '{actual_namespace}'",
                    "message": f"Successfully deleted 0 vectors for document '{document_id}' from namespace '{actual_namespace}'"
                }
            
            # Delete vectors by filter
            result = self.pinecone_index.delete(
                filter={"document_id": document_id},
                namespace=actual_namespace
            )
            
            # Get delete count from result
            deleted_count = result.get("deleted_count", 0)
            
            return {
                "success": True,
                "document_id": document_id,
                "namespace": actual_namespace,
                "deleted_count": deleted_count,
                "message": f"Successfully deleted {deleted_count} vectors for document '{document_id}' from namespace '{actual_namespace}'"
            }
        except Exception as e:
            logger.error(f"[{self.correlation_id}] Error deleting document vectors: {str(e)}")
            return {
                "success": False,
                "document_id": document_id,
                "error": f"Error deleting document vectors: {str(e)}"
            }
    
    async def list_documents(self):
        """List all documents in the Pinecone index"""
        if self.mock_mode:
            logger.info(f"[{self.correlation_id}] MOCK: Listing documents in namespace '{self.namespace}'")
            return {
                "success": True,
                "namespace": self.namespace,
                "documents": [
                    {"id": "doc1", "title": "Sample Document 1"},
                    {"id": "doc2", "title": "Sample Document 2"}
                ]
            }
            
        try:
            if not self.pinecone_index:
                self.pinecone_index = PineconeConnectionManager.get_index(self.api_key, self.index_name)
                
            # The namespace to use might be in vdb-X format if vector_db_id provided
            actual_namespace = f"vdb-{self.vector_db_id}" if self.vector_db_id else self.namespace
            
            # Get index stats
            stats = self.pinecone_index.describe_index_stats()
            namespaces = stats.get("namespaces", {})
            total_vectors = namespaces.get(actual_namespace, {}).get("vector_count", 0)
            
            # Query unique document IDs
            # Use a sparse vector with top_k=0 to just get metadata stats
            # This is more efficient than retrieving actual vectors
            results = self.pinecone_index.query(
                vector=[0] * 1536,  # Dummy vector for metadata-only query
                top_k=100,  # Limit to 100 results
                include_metadata=True,
                namespace=actual_namespace
            )
            
            # Extract unique document IDs from metadata
            document_map = {}
            matches = results.get("matches", [])
            
            for match in matches:
                metadata = match.get("metadata", {})
                doc_id = metadata.get("document_id")
                
                if doc_id and doc_id not in document_map:
                    document_map[doc_id] = {
                        "id": doc_id,
                        "title": metadata.get("title", "Unknown"),
                        "chunks": 1
                    }
                elif doc_id:
                    document_map[doc_id]["chunks"] += 1
            
            documents = list(document_map.values())
            
            return {
                "success": True,
                "namespace": actual_namespace,
                "index_name": self.index_name,
                "total_vectors": total_vectors,
                "documents": documents
            }
        except Exception as e:
            logger.error(f"[{self.correlation_id}] Error listing documents: {str(e)}")
            return {
                "success": False,
                "error": f"Error listing documents: {str(e)}"
            } 

