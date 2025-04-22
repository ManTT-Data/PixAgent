import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any

from app.utils.pdf_processor import PDFProcessor
from app.models.pdf_models import PDFResponse, DeleteDocumentRequest, DocumentsListResponse
from app.api.pdf_websocket import (
    send_pdf_upload_started, 
    send_pdf_upload_progress, 
    send_pdf_upload_completed,
    send_pdf_upload_failed,
    send_pdf_delete_started,
    send_pdf_delete_completed,
    send_pdf_delete_failed
)

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
    user_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None
):
    """
    Upload và xử lý file PDF để tạo embeddings và lưu vào Pinecone
    
    - **file**: File PDF cần xử lý
    - **namespace**: Namespace trong Pinecone để lưu embeddings (mặc định: "Default")
    - **index_name**: Tên index Pinecone (mặc định: "testbot768")
    - **title**: Tiêu đề của tài liệu (tùy chọn)
    - **description**: Mô tả về tài liệu (tùy chọn)
    - **user_id**: ID của người dùng để cập nhật trạng thái qua WebSocket
    """
    try:
        # Kiểm tra file có phải PDF không
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF")
        
        # Tạo file_id và lưu file tạm
        file_id = str(uuid.uuid4())
        temp_file_path = os.path.join(TEMP_UPLOAD_DIR, f"{file_id}.pdf")
        
        # Gửi thông báo bắt đầu xử lý qua WebSocket nếu có user_id
        if user_id:
            await send_pdf_upload_started(user_id, file.filename, file_id)
        
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
        
        # Gửi thông báo tiến độ qua WebSocket
        if user_id:
            await send_pdf_upload_progress(
                user_id, 
                file_id, 
                "file_preparation", 
                0.2, 
                "File saved, preparing for processing"
            )
            
        # Khởi tạo PDF processor
        processor = PDFProcessor(index_name=index_name, namespace=namespace)
        
        # Gửi thông báo bắt đầu embedding qua WebSocket
        if user_id:
            await send_pdf_upload_progress(
                user_id, 
                file_id, 
                "embedding_start", 
                0.4, 
                "Starting to process PDF and create embeddings"
            )
        
        # Xử lý PDF và tạo embeddings
        # Tạo callback function để xử lý cập nhật tiến độ
        async def progress_callback_wrapper(step, progress, message):
            if user_id:
                await send_progress_update(user_id, file_id, step, progress, message)
        
        # Xử lý PDF và tạo embeddings với callback đã được xử lý đúng cách
        result = await processor.process_pdf(
            file_path=temp_file_path,
            document_id=file_id,
            metadata=metadata,
            progress_callback=progress_callback_wrapper
        )
        
        # Nếu thành công, chuyển file vào storage
        if result.get('success'):
            storage_path = os.path.join(STORAGE_DIR, f"{file_id}.pdf")
            shutil.move(temp_file_path, storage_path)
            
            # Gửi thông báo hoàn thành qua WebSocket
            if user_id:
                await send_pdf_upload_completed(
                    user_id,
                    file_id,
                    file.filename,
                    result.get('chunks_processed', 0)
                )
        else:
            # Gửi thông báo lỗi qua WebSocket
            if user_id:
                await send_pdf_upload_failed(
                    user_id,
                    file_id,
                    file.filename,
                    result.get('error', 'Unknown error')
                )
            
        # Dọn dẹp: xóa file tạm nếu vẫn còn
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
        return result
    except Exception as e:
        # Dọn dẹp nếu có lỗi
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
        # Gửi thông báo lỗi qua WebSocket
        if 'user_id' in locals() and user_id and 'file_id' in locals():
            await send_pdf_upload_failed(
                user_id,
                file_id,
                file.filename,
                str(e)
            )
            
        return PDFResponse(
            success=False,
            error=str(e)
        )

# Function để gửi cập nhật tiến độ - được sử dụng trong callback
async def send_progress_update(user_id, document_id, step, progress, message):
    if user_id:
        await send_pdf_upload_progress(user_id, document_id, step, progress, message)

# Endpoint xóa tài liệu
@router.delete("/namespace", response_model=PDFResponse)
async def delete_namespace(
    namespace: str = "Default",
    index_name: str = "testbot768",
    user_id: Optional[str] = None
):
    """
    Xóa toàn bộ embeddings trong một namespace từ Pinecone (tương ứng xoá namespace)

    - **namespace**: Namespace trong Pinecone (mặc định: "Default")
    - **index_name**: Tên index Pinecone (mặc định: "testbot768")
    - **user_id**: ID của người dùng để cập nhật trạng thái qua WebSocket
    """
    try:
        # Gửi thông báo bắt đầu xóa qua WebSocket
        if user_id:
            await send_pdf_delete_started(user_id, namespace)
            
        processor = PDFProcessor(index_name=index_name, namespace=namespace)
        result = await processor.delete_namespace()
        
        # Gửi thông báo kết quả qua WebSocket
        if user_id:
            if result.get('success'):
                await send_pdf_delete_completed(user_id, namespace)
            else:
                await send_pdf_delete_failed(user_id, namespace, result.get('error', 'Unknown error'))
                
        return result
    except Exception as e:
        # Gửi thông báo lỗi qua WebSocket
        if user_id:
            await send_pdf_delete_failed(user_id, namespace, str(e))
            
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