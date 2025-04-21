import os
import time
import uuid
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import logging

from app.database.pinecone import get_pinecone_index, init_pinecone

# Cấu hình logging
logger = logging.getLogger(__name__)

# Khởi tạo embeddings model
embeddings_model = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

class PDFProcessor:
    """Lớp xử lý file PDF và tạo embeddings"""
    
    def __init__(self, index_name="testbot768", namespace="Default"):
        """Khởi tạo với tên index và namespace Pinecone mặc định"""
        self.index_name = index_name
        self.namespace = namespace
        self.pinecone_index = None
        
    def _init_pinecone_connection(self):
        """Khởi tạo kết nối đến Pinecone"""
        try:
            # Sử dụng singleton pattern từ module database.pinecone
            self.pinecone_index = get_pinecone_index()
            if not self.pinecone_index:
                logger.error("Không thể kết nối đến Pinecone")
                return False
            return True
        except Exception as e:
            logger.error(f"Lỗi khi kết nối Pinecone: {str(e)}")
            return False
            
    async def process_pdf(self, file_path, document_id=None, metadata=None):
        """
        Xử lý file PDF, chia thành chunks và tạo embeddings
        
        Args:
            file_path (str): Đường dẫn tới file PDF
            document_id (str, optional): ID của tài liệu, nếu không cung cấp sẽ tạo ID mới
            metadata (dict, optional): Metadata bổ sung cho tài liệu
            
        Returns:
            dict: Thông tin kết quả xử lý gồm document_id và số chunks đã xử lý
        """
        try:
            # Khởi tạo kết nối Pinecone nếu chưa có
            if not self.pinecone_index:
                if not self._init_pinecone_connection():
                    return {"success": False, "error": "Không thể kết nối đến Pinecone"}
            
            # Tạo document_id nếu không có
            if not document_id:
                document_id = str(uuid.uuid4())
            
            # Đọc file PDF bằng PyPDFLoader
            logger.info(f"Đang đọc file PDF: {file_path}")
            loader = PyPDFLoader(file_path)
            pages = loader.load()
            
            # Trích xuất và nối text từ tất cả các trang
            all_text = ""
            for page in pages:
                all_text += page.page_content + "\n"
            
            # Chia văn bản thành các chunk
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=300)
            chunks = text_splitter.split_text(all_text)
            
            logger.info(f"Đã chia file PDF thành {len(chunks)} chunks")
            
            # Xử lý embedding cho từng chunk và upsert lên Pinecone
            vectors = []
            for i, chunk in enumerate(chunks):
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
            
            return {
                "success": True,
                "document_id": document_id,
                "chunks_processed": len(chunks),
                "total_text_length": len(all_text)
            }
            
        except Exception as e:
            logger.error(f"Lỗi khi xử lý PDF: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _upsert_vectors(self, vectors):
        """Upsert vectors vào Pinecone"""
        try:
            if not vectors:
                return
                
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
        if not self.pinecone_index and not self._init_pinecone_connection():
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
            if not self.pinecone_index:
                if not self._init_pinecone_connection():
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