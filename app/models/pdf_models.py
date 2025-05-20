from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class PDFUploadRequest(BaseModel):
    """Request model cho upload PDF"""
    namespace: Optional[str] = Field("Default", description="Namespace trong Pinecone")
    index_name: Optional[str] = Field("testbot768", description="Tên index trong Pinecone")
    title: Optional[str] = Field(None, description="Tiêu đề của tài liệu")
    description: Optional[str] = Field(None, description="Mô tả về tài liệu")
    vector_database_id: Optional[int] = Field(None, description="ID của vector database trong PostgreSQL để sử dụng")

class PDFResponse(BaseModel):
    """Response model cho các endpoints liên quan đến PDF."""
    success: bool = Field(False, description="Kết quả xử lý: true/false")
    document_id: Optional[str] = Field(None, description="ID của tài liệu đã xử lý")
    document_database_id: Optional[int] = Field(None, description="ID của tài liệu trong PostgreSQL (nếu có)")
    chunks_processed: Optional[int] = Field(None, description="Số lượng chunks đã xử lý")
    total_text_length: Optional[int] = Field(None, description="Tổng kích thước text đã xử lý")
    error: Optional[str] = Field(None, description="Thông báo lỗi (nếu có)")
    warning: Optional[str] = Field(None, description="Cảnh báo (nếu có)")
    message: Optional[str] = Field(None, description="Thông báo thành công")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "chunks_processed": 25,
                "total_text_length": 50000,
                "message": "Successfully processed document"
            }
        }

class DeleteDocumentRequest(BaseModel):
    """Request model cho xóa document"""
    document_id: str = Field(..., description="ID của tài liệu cần xóa")
    namespace: Optional[str] = Field("Default", description="Namespace trong Pinecone")
    index_name: Optional[str] = Field("testbot768", description="Tên index trong Pinecone")
    vector_database_id: Optional[int] = Field(None, description="ID của vector database trong PostgreSQL")

class DocumentsListResponse(BaseModel):
    """Response model cho danh sách documents"""
    success: bool = Field(False, description="Kết quả xử lý: true/false")
    total_vectors: Optional[int] = Field(None, description="Tổng số vectors trong namespace")
    namespace: Optional[str] = Field(None, description="Namespace đã truy vấn")
    index_name: Optional[str] = Field(None, description="Tên index đã truy vấn")
    documents: Optional[List[Dict[str, Any]]] = Field(None, description="Danh sách documents")
    postgresql_documents: Optional[List[Dict[str, Any]]] = Field(None, description="Danh sách documents từ PostgreSQL")
    postgresql_document_count: Optional[int] = Field(None, description="Số lượng documents từ PostgreSQL")
    error: Optional[str] = Field(None, description="Thông báo lỗi (nếu có)")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "total_vectors": 5000,
                "namespace": "Default",
                "index_name": "testbot768"
            }
        } 