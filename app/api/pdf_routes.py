import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any

from app.utils.pdf_processor import PDFProcessor
from app.models.pdf_models import PDFResponse, DeleteDocumentRequest, DocumentsListResponse

# Khởi tạo router
router = APIRouter(
    prefix="/pdf",
    tags=["PDF Processing"],
)

# Thư mục lưu file tạm
TEMP_UPLOAD_DIR = "./uploads/temp"
STORAGE_DIR = "./uploads/pdfs"

# Đảm bảo thư mục upload tồn tại
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)

# Endpoint upload và xử lý PDF
@router.post("/upload", response_model=PDFResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    namespace: str = Form("Default"),
    index_name: str = Form("testbot768"),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None
):
    """
    Upload và xử lý file PDF để tạo embeddings và lưu vào Pinecone
    
    - **file**: File PDF cần xử lý
    - **namespace**: Namespace trong Pinecone để lưu embeddings (mặc định: "Default")
    - **index_name**: Tên index Pinecone (mặc định: "testbot768")
    - **title**: Tiêu đề của tài liệu (tùy chọn)
    - **description**: Mô tả về tài liệu (tùy chọn)
    """
    try:
        # Kiểm tra file có phải PDF không
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF")
        
        # Tạo file_id và lưu file tạm
        file_id = str(uuid.uuid4())
        temp_file_path = os.path.join(TEMP_UPLOAD_DIR, f"{file_id}.pdf")
        
        # Lưu file
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Tạo metadata
        metadata = {
            "filename": file.filename,
            "content_type": file.content_type
        }
        
        if title:
            metadata["title"] = title
        if description:
            metadata["description"] = description
            
        # Khởi tạo PDF processor
        processor = PDFProcessor(index_name=index_name, namespace=namespace)
        
        # Xử lý PDF và tạo embeddings
        result = await processor.process_pdf(
            file_path=temp_file_path,
            document_id=file_id,
            metadata=metadata
        )
        
        # Nếu thành công, chuyển file vào storage
        if result.get('success'):
            storage_path = os.path.join(STORAGE_DIR, f"{file_id}.pdf")
            shutil.move(temp_file_path, storage_path)
            
        # Dọn dẹp: xóa file tạm nếu vẫn còn
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
        return result
    except Exception as e:
        # Dọn dẹp nếu có lỗi
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
        return PDFResponse(
            success=False,
            error=str(e)
        )

# Endpoint xóa tài liệu
@router.delete("/namespace", response_model=PDFResponse)
async def delete_namespace(
    namespace: str = "Default",
    index_name: str = "testbot768"
):
    """
    Xóa toàn bộ embeddings trong một namespace từ Pinecone (tương ứng xoá namespace)

    - **namespace**: Namespace trong Pinecone (mặc định: "Default")
    - **index_name**: Tên index Pinecone (mặc định: "testbot768")
    """
    try:
        processor = PDFProcessor(index_name=index_name, namespace=namespace)
        result = await processor.delete_namespace()
        return result
    except Exception as e:
        return PDFResponse(
            success=False,
            error=str(e)
        )

# Endpoint lấy danh sách tài liệu
@router.get("/documents", response_model=DocumentsListResponse)
async def get_documents(namespace: str = "Default", index_name: str = "testbot768"):
    """
    Lấy thông tin về tất cả tài liệu đã được embed
    
    - **namespace**: Namespace trong Pinecone (mặc định: "Default")
    - **index_name**: Tên index Pinecone (mặc định: "testbot768")
    """
    try:
        # Khởi tạo PDF processor
        processor = PDFProcessor(index_name=index_name, namespace=namespace)
        
        # Lấy danh sách documents
        result = await processor.list_documents()
        
        return result
    except Exception as e:
        return DocumentsListResponse(
            success=False,
            error=str(e)
        ) 