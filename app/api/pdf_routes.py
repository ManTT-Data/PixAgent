import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.utils.pdf_processor import PDFProcessor
from app.models.pdf_models import PDFResponse, DeleteDocumentRequest, DocumentsListResponse
from app.database.postgresql import get_db
from app.database.models import VectorDatabase, Document, VectorStatus, DocumentContent
from datetime import datetime
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

# Thư mục lưu file tạm - sử dụng /tmp để tránh lỗi quyền truy cập
TEMP_UPLOAD_DIR = "/tmp/uploads/temp"
STORAGE_DIR = "/tmp/uploads/pdfs"

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
    vector_database_id: Optional[int] = Form(None),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Upload và xử lý file PDF để tạo embeddings và lưu vào Pinecone
    
    - **file**: File PDF cần xử lý
    - **namespace**: Namespace trong Pinecone để lưu embeddings (mặc định: "Default")
    - **index_name**: Tên index Pinecone (mặc định: "testbot768")
    - **title**: Tiêu đề của tài liệu (tùy chọn)
    - **description**: Mô tả về tài liệu (tùy chọn)
    - **user_id**: ID của người dùng để cập nhật trạng thái qua WebSocket
    - **vector_database_id**: ID của vector database trong PostgreSQL (tùy chọn)
    """
    try:
        # Kiểm tra file có phải PDF không
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF")
        
        # Nếu có vector_database_id, lấy thông tin từ PostgreSQL
        api_key = None
        vector_db = None
        
        if vector_database_id:
            vector_db = db.query(VectorDatabase).filter(
                VectorDatabase.id == vector_database_id,
                VectorDatabase.status == "active"
            ).first()
            
            if not vector_db:
                raise HTTPException(status_code=404, detail="Vector database không tồn tại hoặc không hoạt động")
            
            # Sử dụng thông tin từ vector database
            api_key = vector_db.api_key
            index_name = vector_db.pinecone_index
        
        # Tạo file_id và lưu file tạm
        file_id = str(uuid.uuid4())
        temp_file_path = os.path.join(TEMP_UPLOAD_DIR, f"{file_id}.pdf")
        
        # Gửi thông báo bắt đầu xử lý qua WebSocket nếu có user_id
        if user_id:
            await send_pdf_upload_started(user_id, file.filename, file_id)
        
        # Lưu file
        file_content = await file.read()
        with open(temp_file_path, "wb") as buffer:
            buffer.write(file_content)
            
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
        
        # Lưu thông tin tài liệu vào PostgreSQL nếu có vector_database_id
        if vector_database_id and vector_db:
            # Create document record without file content
            document = Document(
                name=title or file.filename,
                file_type="pdf",
                content_type=file.content_type,
                size=len(file_content),
                is_embedded=False,
                vector_database_id=vector_database_id
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            
            # Create document content record to store binary data separately
            document_content = DocumentContent(
                document_id=document.id,
                file_content=file_content
            )
            db.add(document_content)
            db.commit()
            
            # Tạo vector status record
            vector_status = VectorStatus(
                document_id=document.id,
                vector_database_id=vector_database_id,
                status="pending"
            )
            db.add(vector_status)
            db.commit()
            
        # Khởi tạo PDF processor với API key nếu có
        processor = PDFProcessor(index_name=index_name, namespace=namespace, api_key=api_key)
        
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
            
            # Cập nhật trạng thái trong PostgreSQL nếu có vector_database_id
            if vector_database_id and 'document' in locals() and 'vector_status' in locals():
                vector_status.status = "completed"
                vector_status.embedded_at = datetime.now()
                vector_status.vector_id = file_id
                document.is_embedded = True
                db.commit()
            
            # Gửi thông báo hoàn thành qua WebSocket
            if user_id:
                await send_pdf_upload_completed(
                    user_id,
                    file_id,
                    file.filename,
                    result.get('chunks_processed', 0)
                )
        else:
            # Cập nhật trạng thái lỗi trong PostgreSQL nếu có vector_database_id
            if vector_database_id and 'vector_status' in locals():
                vector_status.status = "failed"
                vector_status.error_message = result.get('error', 'Unknown error')
                db.commit()
                
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
            
        # Cập nhật trạng thái lỗi trong PostgreSQL nếu có vector_database_id
        if 'vector_database_id' in locals() and vector_database_id and 'vector_status' in locals():
            vector_status.status = "failed"
            vector_status.error_message = str(e)
            db.commit()
            
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