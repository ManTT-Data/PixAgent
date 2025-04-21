from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class PDFUploadRequest(BaseModel):
    """Request model cho upload PDF"""
    namespace: Optional[str] = Field("Default", description="Namespace trong Pinecone")
    index_name: Optional[str] = Field("testbot768", description="Tên index trong Pinecone")
    title: Optional[str] = Field(None, description="Tiêu đề của tài liệu")
    description: Optional[str] = Field(None, description="Mô tả về tài liệu")

class PDFResponse(BaseModel):
    """Response model cho xử lý PDF"""
    success: bool = Field(..., description="Trạng thái xử lý thành công hay không")
    document_id: Optional[str] = Field(None, description="ID của tài liệu")
    chunks_processed: Optional[int] = Field(None, description="Số lượng chunks đã xử lý")
    total_text_length: Optional[int] = Field(None, description="Tổng độ dài văn bản")
    error: Optional[str] = Field(None, description="Thông báo lỗi nếu có")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "chunks_processed": 25,
                "total_text_length": 50000
            }
        }

class DeleteDocumentRequest(BaseModel):
    """Request model cho xóa document"""
    document_id: str = Field(..., description="ID của tài liệu cần xóa")
    namespace: Optional[str] = Field("Default", description="Namespace trong Pinecone")
    index_name: Optional[str] = Field("testbot768", description="Tên index trong Pinecone")

class DocumentsListResponse(BaseModel):
    """Response model cho lấy danh sách tài liệu"""
    success: bool = Field(..., description="Trạng thái xử lý thành công hay không")
    total_vectors: Optional[int] = Field(None, description="Tổng số vectors trong index")
    namespace: Optional[str] = Field(None, description="Namespace đang sử dụng")
    index_name: Optional[str] = Field(None, description="Tên index đang sử dụng")
    error: Optional[str] = Field(None, description="Thông báo lỗi nếu có")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "total_vectors": 5000,
                "namespace": "Default",
                "index_name": "testbot768"
            }
        } 