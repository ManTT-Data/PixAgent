import os
import time
import uuid
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import logging
from pinecone import Pinecone

from app.database.pinecone import get_pinecone_index, init_pinecone

# Cấu hình logging
logger = logging.getLogger(__name__)

# Khởi tạo embeddings model
embeddings_model = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

class PDFProcessor:
    """Lớp xử lý file PDF và tạo embeddings"""
    
    def __init__(self, index_name="testbot768", namespace="Default", api_key=None, mock_mode=False):
        """Khởi tạo với tên index, namespace Pinecone và API key"""
        self.index_name = index_name
        self.namespace = namespace
        self.pinecone_index = None
        self.api_key = api_key
        self.pinecone_client = None
        self.mock_mode = mock_mode  # Add mock mode for testing
        
    def _init_pinecone_connection(self):
        """Khởi tạo kết nối đến Pinecone với API mới"""
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
                
            if not self.api_key or not self.index_name:
                logger.error("Pinecone API key or index name not set in environment variables")
                return None
            
            # Initialize Pinecone client using the new API
            self.pinecone_client = Pinecone(api_key=self.api_key)
            
            # Get the index
            index_list = self.pinecone_client.list_indexes()
            if not hasattr(index_list, 'names') or self.index_name not in index_list.names():
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
        Xử lý file PDF, chia thành chunks và tạo embeddings
        
        Args:
            file_path (str): Đường dẫn tới file PDF
            document_id (str, optional): ID của tài liệu, nếu không cung cấp sẽ tạo ID mới
            metadata (dict, optional): Metadata bổ sung cho tài liệu
            progress_callback (callable, optional): Callback function để cập nhật tiến độ
            
        Returns:
            dict: Thông tin kết quả xử lý gồm document_id và số chunks đã xử lý
        """
        try:
            # Khởi tạo kết nối Pinecone nếu chưa có
            self.pinecone_index = self._init_pinecone_connection()
            if not self.pinecone_index:
                return {"success": False, "error": "Không thể kết nối đến Pinecone"}
            
            # Tạo document_id nếu không có
            if not document_id:
                document_id = str(uuid.uuid4())
            
            # Đọc file PDF bằng PyPDFLoader
            logger.info(f"Đang đọc file PDF: {file_path}")
            if progress_callback:
                await progress_callback("pdf_loading", 0.5, "Loading PDF file")
                
            loader = PyPDFLoader(file_path)
            pages = loader.load()
            
            # Trích xuất và nối text từ tất cả các trang
            all_text = ""
            for page in pages:
                all_text += page.page_content + "\n"
            
            if progress_callback:
                await progress_callback("text_extraction", 0.6, "Extracted text from PDF")
                
            # Chia văn bản thành các chunk
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=300)
            chunks = text_splitter.split_text(all_text)
            
            logger.info(f"Đã chia file PDF thành {len(chunks)} chunks")
            if progress_callback:
                await progress_callback("chunking", 0.7, f"Split document into {len(chunks)} chunks")
            
            # Xử lý embedding cho từng chunk và upsert lên Pinecone
            vectors = []
            for i, chunk in enumerate(chunks):
                # Cập nhật tiến độ embedding
                if progress_callback and i % 5 == 0:  # Cập nhật sau mỗi 5 chunks để tránh quá nhiều thông báo
                    embedding_progress = 0.7 + (0.3 * (i / len(chunks)))
                    await progress_callback("embedding", embedding_progress, f"Processing chunk {i+1}/{len(chunks)}")
                
                # Tạo vector embedding cho từng chunk
                vector = embeddings_model.embed_query(chunk)
                
                # Chuẩn bị metadata cho vector
                vector_metadata = {
                    "document_id": document_id,
                    "chunk_index": i,
                    "text": chunk
                }
                
                # Thêm metadata bổ sung nếu có
                if metadata:
                    for key, value in metadata.items():
                        if key not in vector_metadata:
                            vector_metadata[key] = value
                
                # Thêm vector vào danh sách để upsert
                vectors.append({
                    "id": f"{document_id}_{i}",
                    "values": vector,
                    "metadata": vector_metadata
                })
                
                # Upsert mỗi 100 vectors để tránh quá lớn
                if len(vectors) >= 100:
                    await self._upsert_vectors(vectors)
                    vectors = []
            
            # Upsert các vectors còn lại
            if vectors:
                await self._upsert_vectors(vectors)
            
            logger.info(f"Đã embedding và lưu {len(chunks)} chunks từ PDF với document_id: {document_id}")
            
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
            logger.error(f"Lỗi khi xử lý PDF: {str(e)}")
            if progress_callback:
                await progress_callback("error", 0, f"Error processing PDF: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _upsert_vectors(self, vectors):
        """Upsert vectors vào Pinecone"""
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
            
            logger.info(f"Đã upsert {len(vectors)} vectors vào Pinecone")
            return result
        except Exception as e:
            logger.error(f"Lỗi khi upsert vectors: {str(e)}")
            raise
    
    async def delete_namespace(self):
        """
        Xóa toàn bộ vectors trong namespace hiện tại (tương đương xoá namespace).
        """
        # Khởi tạo kết nối nếu cần
        self.pinecone_index = self._init_pinecone_connection()
        if not self.pinecone_index:
            return {"success": False, "error": "Không thể kết nối đến Pinecone"}

        try:
            # delete_all=True sẽ xóa toàn bộ vectors trong namespace
            result = self.pinecone_index.delete(
                delete_all=True,
                namespace=self.namespace
            )
            logger.info(f"Đã xóa namespace '{self.namespace}' (tất cả vectors).")
            return {"success": True, "detail": result}
        except Exception as e:
            logger.error(f"Lỗi khi xóa namespace '{self.namespace}': {e}")
            return {"success": False, "error": str(e)}
    
    async def list_documents(self):
        """Lấy danh sách tất cả document_id từ Pinecone"""
        try:
            # Khởi tạo kết nối Pinecone nếu chưa có
            self.pinecone_index = self._init_pinecone_connection()
            if not self.pinecone_index:
                return {"success": False, "error": "Không thể kết nối đến Pinecone"}
            
            # Lấy thông tin index
            stats = self.pinecone_index.describe_index_stats()
            
            # Thực hiện truy vấn để lấy danh sách tất cả document_id duy nhất
            # Phương pháp này có thể không hiệu quả với dataset lớn, nhưng là cách đơn giản nhất
            # Trong thực tế, nên lưu danh sách document_id trong một database riêng
            
            return {
                "success": True,
                "total_vectors": stats.get('total_vector_count', 0),
                "namespace": self.namespace,
                "index_name": self.index_name
            }
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách documents: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            } 