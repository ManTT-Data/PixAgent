import os
import shutil
import uuid
import sys
import traceback
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import os.path
import logging
import tempfile
import time
import json
from datetime import datetime

from app.utils.pdf_processor import PDFProcessor
from app.models.pdf_models import PDFResponse, DeleteDocumentRequest, DocumentsListResponse
from app.database.postgresql import get_db
from app.database.models import VectorDatabase, Document, VectorStatus, ApiKey, DocumentContent
from app.api.pdf_websocket import (
    send_pdf_upload_started, 
    send_pdf_upload_progress, 
    send_pdf_upload_completed,
    send_pdf_upload_failed,
    send_pdf_delete_started,
    send_pdf_delete_completed,
    send_pdf_delete_failed
)

# Setup logger
logger = logging.getLogger(__name__)

# Add a stream handler for PDF debug logging
pdf_debug_logger = logging.getLogger("pdf_debug_api")
pdf_debug_logger.setLevel(logging.DEBUG)

# Check if a stream handler already exists, add one if not
if not any(isinstance(h, logging.StreamHandler) for h in pdf_debug_logger.handlers):
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    pdf_debug_logger.addHandler(stream_handler)

# Initialize router
router = APIRouter(
    prefix="/pdf",
    tags=["PDF Processing"],
)

# Constants - Use system temp directory instead of creating our own
TEMP_UPLOAD_DIR = tempfile.gettempdir()
STORAGE_DIR = tempfile.gettempdir()  # Also use system temp for storage

USE_MOCK_MODE = False  # Disabled - using real database with improved connection handling
logger.info(f"PDF API starting with USE_MOCK_MODE={USE_MOCK_MODE}")

# Helper function to log with timestamp
def log_with_timestamp(message: str, level: str = "info", error: Exception = None):
    """Add timestamps to log messages and log to the PDF debug logger if available"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"{timestamp} - {message}"
    
    if level.lower() == "debug":
        logger.debug(full_message)
        pdf_debug_logger.debug(full_message)
    elif level.lower() == "info":
        logger.info(full_message)
        pdf_debug_logger.info(full_message)
    elif level.lower() == "warning":
        logger.warning(full_message)
        pdf_debug_logger.warning(full_message)
    elif level.lower() == "error":
        logger.error(full_message)
        pdf_debug_logger.error(full_message)
        if error:
            logger.error(traceback.format_exc())
            pdf_debug_logger.error(traceback.format_exc())
    else:
        logger.info(full_message)
        pdf_debug_logger.info(full_message)

# Helper function to log debug information during upload
def log_upload_debug(correlation_id: str, message: str, error: Exception = None):
    """Log detailed debug information about PDF uploads"""
    pdf_debug_logger.debug(f"[{correlation_id}] {message}")
    if error:
        pdf_debug_logger.error(f"[{correlation_id}] Error: {str(error)}")
        pdf_debug_logger.error(traceback.format_exc())

# Helper function to send progress updates
async def send_progress_update(user_id, file_id, step, progress=0.0, message=""):
    """Send PDF processing progress updates via WebSocket"""
    try:
        await send_pdf_upload_progress(user_id, file_id, step, progress, message)
    except Exception as e:
        logger.error(f"Error sending progress update: {e}")
        logger.error(traceback.format_exc())

# Function with fixed indentation for the troublesome parts
async def handle_pdf_processing_result(result, correlation_id, user_id, file_id, filename, document, vector_status, 
                                    vector_database_id, temp_file_path, db, is_pdf, mock_mode):
    """Fixed version of the code with proper indentation"""
    # If successful, update status but don't try to permanently store files
    if result.get('success'):
        try:
            log_upload_debug(correlation_id, f"Processed file successfully - no permanent storage in Hugging Face environment")
        except Exception as move_error:
            log_upload_debug(correlation_id, f"Error in storage handling: {move_error}", move_error)
        
        # Update status in PostgreSQL
        if vector_database_id and document and vector_status:
            try:
                log_upload_debug(correlation_id, f"Updating vector status to 'completed' for document ID {document.id}")
                vector_status.status = "completed"
                vector_status.embedded_at = datetime.now()
                vector_status.vector_id = file_id
                document.is_embedded = True
                db.commit()
                log_upload_debug(correlation_id, f"Database status updated successfully")
            except Exception as db_error:
                log_upload_debug(correlation_id, f"Error updating database status: {db_error}", db_error)
        
        # Send completion notification via WebSocket
        if user_id:
            try:
                await send_pdf_upload_completed(
                    user_id,
                    file_id,
                    filename,
                    result.get('chunks_processed', 0)
                )
                log_upload_debug(correlation_id, f"Sent upload completed notification to user {user_id}")
            except Exception as ws_error:
                log_upload_debug(correlation_id, f"Error sending WebSocket notification: {ws_error}", ws_error)
            
        # Add document information to the result
        if document:
            result["document_database_id"] = document.id
            
        # Include mock_mode in response
        result["mock_mode"] = mock_mode
    else:
        log_upload_debug(correlation_id, f"PDF processing failed: {result.get('error', 'Unknown error')}")
        
        # Update error status in PostgreSQL
        if vector_database_id and document and vector_status:
            try:
                log_upload_debug(correlation_id, f"Updating vector status to 'failed' for document ID {document.id}")
                vector_status.status = "failed"
                vector_status.error_message = result.get('error', 'Unknown error')
                db.commit()
                log_upload_debug(correlation_id, f"Database status updated for failure")
            except Exception as db_error:
                log_upload_debug(correlation_id, f"Error updating database status for failure: {db_error}", db_error)
            
        # Send failure notification via WebSocket
        if user_id:
            try:
                await send_pdf_upload_failed(
                    user_id,
                    file_id,
                    filename,
                    result.get('error', 'Unknown error')
                )
                log_upload_debug(correlation_id, f"Sent upload failed notification to user {user_id}")
            except Exception as ws_error:
                log_upload_debug(correlation_id, f"Error sending WebSocket notification: {ws_error}", ws_error)
        
    # Cleanup: delete temporary file if it still exists
    if os.path.exists(temp_file_path):
        try:
            os.remove(temp_file_path)
            log_upload_debug(correlation_id, f"Removed temporary file {temp_file_path}")
        except Exception as cleanup_error:
            log_upload_debug(correlation_id, f"Error removing temporary file: {cleanup_error}", cleanup_error)
    
    log_upload_debug(correlation_id, f"Upload request completed with success={result.get('success', False)}")
    return result

# Endpoint for uploading and processing PDFs
@router.post("/upload", response_model=PDFResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    namespace: str = Form("Default"),
    index_name: str = Form("testbot768"),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    vector_database_id: Optional[int] = Form(None),
    content_type: Optional[str] = Form(None),  # Add content_type parameter
    background_tasks: BackgroundTasks = None,
    mock_mode: bool = Form(False),  # Set to False to use real database
    db: Session = Depends(get_db)
):
    """
    Upload and process PDF file to create embeddings and store in Pinecone
    
    - **file**: PDF file to process
    - **namespace**: Namespace in Pinecone to store embeddings (default: "Default")
    - **index_name**: Name of Pinecone index (default: "testbot768")
    - **title**: Document title (optional)
    - **description**: Document description (optional)
    - **user_id**: User ID for WebSocket status updates
    - **vector_database_id**: ID of vector database in PostgreSQL (optional)
    - **content_type**: Content type of the file (optional)
    - **mock_mode**: Simulate Pinecone operations instead of performing real calls (default: false)
    """
    # Generate request ID for tracking
    correlation_id = str(uuid.uuid4())[:8]
    logger.info(f"[{correlation_id}] PDF upload request received: ns={namespace}, index={index_name}, user={user_id}")
    log_upload_debug(correlation_id, f"Upload request: vector_db_id={vector_database_id}, mock_mode={mock_mode}")
    
    try:
        # Check file type - accept both PDF and plaintext for testing
        is_pdf = file.filename.lower().endswith('.pdf')
        is_text = file.filename.lower().endswith(('.txt', '.md', '.html'))
        
        log_upload_debug(correlation_id, f"File type check: is_pdf={is_pdf}, is_text={is_text}, filename={file.filename}")
        
        if not (is_pdf or is_text):
            if not mock_mode:
                # In real mode, only accept PDFs
                log_upload_debug(correlation_id, f"Rejecting non-PDF file in real mode: {file.filename}")
                raise HTTPException(status_code=400, detail="Only PDF files are accepted")
            else:
                # In mock mode, convert any file to text for testing
                logger.warning(f"[{correlation_id}] Non-PDF file uploaded in mock mode: {file.filename} - will treat as text")
        
        # If vector_database_id provided, get info from PostgreSQL
        api_key = None
        vector_db = None
        
        if vector_database_id:
            log_upload_debug(correlation_id, f"Looking up vector database ID {vector_database_id}")
            
            vector_db = db.query(VectorDatabase).filter(
                VectorDatabase.id == vector_database_id,
                VectorDatabase.status == "active"
            ).first()
            if not vector_db:
                return PDFResponse(
                    success=False,
                    error=f"Vector database with ID {vector_database_id} not found or inactive"
                )
            
            log_upload_debug(correlation_id, f"Found vector database: id={vector_db.id}, name={vector_db.name}, index={vector_db.pinecone_index}")
            
            # Use vector database information
            # Try to get API key from relationship
            log_upload_debug(correlation_id, f"Trying to get API key for vector database {vector_database_id}")
            
            # Log available attributes
            vector_db_attrs = dir(vector_db)
            log_upload_debug(correlation_id, f"Vector DB attributes: {vector_db_attrs}")
            
            if hasattr(vector_db, 'api_key_ref') and vector_db.api_key_ref:
                log_upload_debug(correlation_id, f"Using API key from relationship for vector database ID {vector_database_id}")
                log_upload_debug(correlation_id, f"api_key_ref type: {type(vector_db.api_key_ref)}")
                log_upload_debug(correlation_id, f"api_key_ref attributes: {dir(vector_db.api_key_ref)}")
                
                if hasattr(vector_db.api_key_ref, 'key_value'):
                    api_key = vector_db.api_key_ref.key_value
                    # Log first few chars of API key for debugging
                    key_prefix = api_key[:4] + "..." if api_key and len(api_key) > 4 else "invalid/empty"
                    log_upload_debug(correlation_id, f"API key retrieved: {key_prefix}, length: {len(api_key) if api_key else 0}")
                    logger.info(f"[{correlation_id}] Using API key from relationship for vector database ID {vector_database_id}")
                else:
                    log_upload_debug(correlation_id, f"api_key_ref does not have key_value attribute")
            elif hasattr(vector_db, 'api_key') and vector_db.api_key:
                # Fallback to direct api_key if needed (deprecated)
                api_key = vector_db.api_key
                key_prefix = api_key[:4] + "..." if api_key and len(api_key) > 4 else "invalid/empty"
                log_upload_debug(correlation_id, f"Using deprecated direct api_key: {key_prefix}")
                logger.warning(f"[{correlation_id}] Using deprecated direct api_key for vector database ID {vector_database_id}")
            else:
                log_upload_debug(correlation_id, "No API key found in vector database")
            
            # Use index from vector database
            index_name = vector_db.pinecone_index
            log_upload_debug(correlation_id, f"Using index name '{index_name}' from vector database")
            logger.info(f"[{correlation_id}] Using index name '{index_name}' from vector database")
        
        # Generate file_id and save temporary file
        file_id = str(uuid.uuid4())
        temp_file_path = os.path.join(TEMP_UPLOAD_DIR, f"{file_id}{'.pdf' if is_pdf else '.txt'}")
        log_upload_debug(correlation_id, f"Generated file_id: {file_id}, temp path: {temp_file_path}")
        
        # Send notification of upload start via WebSocket if user_id provided
        if user_id:
            try:
                await send_pdf_upload_started(user_id, file.filename, file_id)
                log_upload_debug(correlation_id, f"Sent upload started notification to user {user_id}")
            except Exception as ws_error:
                log_upload_debug(correlation_id, f"Error sending WebSocket notification: {ws_error}", ws_error)
        
        # Save file
        log_upload_debug(correlation_id, f"Reading file content")
        file_content = await file.read()
        log_upload_debug(correlation_id, f"File size: {len(file_content)} bytes")
        
        with open(temp_file_path, "wb") as buffer:
            buffer.write(file_content)
        log_upload_debug(correlation_id, f"File saved to {temp_file_path}")
            
        # Create metadata
        metadata = {
            "filename": file.filename,
            "content_type": file.content_type
        }
        
        # Use provided content_type or fallback to file.content_type
        actual_content_type = content_type or file.content_type
        log_upload_debug(correlation_id, f"Using content_type: {actual_content_type}")
        
        if not actual_content_type:
            # Fallback content type based on file extension
            if is_pdf:
                actual_content_type = "application/pdf"
            elif is_text:
                actual_content_type = "text/plain"
            else:
                actual_content_type = "application/octet-stream"
                
            log_upload_debug(correlation_id, f"No content_type provided, using fallback: {actual_content_type}")
            
        metadata["content_type"] = actual_content_type
        
        if title:
            metadata["title"] = title
        else:
            # Use filename as title if not provided
            title = file.filename
            metadata["title"] = title
            
        if description:
            metadata["description"] = description
        
        # Send progress update via WebSocket
        if user_id:
            try:
                await send_progress_update(
                user_id, 
                file_id, 
                "file_preparation", 
                0.2, 
                "File saved, preparing for processing"
            )
                log_upload_debug(correlation_id, f"Sent file preparation progress to user {user_id}")
            except Exception as ws_error:
                log_upload_debug(correlation_id, f"Error sending progress update: {ws_error}", ws_error)
        
        # Create document record - do this regardless of mock mode
        document = None
        vector_status = None
        
        if vector_database_id and vector_db:
            log_upload_debug(correlation_id, f"Creating PostgreSQL records for document with vector_database_id={vector_database_id}")
            
            # Create document record without file content
            try:
                document = Document(
                    name=title or file.filename,
                    file_type="pdf" if is_pdf else "text",
                    content_type=actual_content_type,  # Use the actual_content_type here
                    size=len(file_content),
                    is_embedded=False,
                    vector_database_id=vector_database_id
                )
                db.add(document)
                db.commit()
                db.refresh(document)
                log_upload_debug(correlation_id, f"Created document record: id={document.id}")
            except Exception as doc_error:
                log_upload_debug(correlation_id, f"Error creating document record: {doc_error}", doc_error)
                raise
            
            # Create document content record to store binary data separately
            try:
                document_content = DocumentContent(
                    document_id=document.id,
                    file_content=file_content
                )
                db.add(document_content)
                db.commit()
                log_upload_debug(correlation_id, f"Created document content record for document ID {document.id}")
            except Exception as content_error:
                log_upload_debug(correlation_id, f"Error creating document content: {content_error}", content_error)
                raise
            
            # Create vector status record
            try:
                vector_status = VectorStatus(
                    document_id=document.id,
                    vector_database_id=vector_database_id,
                    status="pending"
                )
                db.add(vector_status)
                db.commit()
                log_upload_debug(correlation_id, f"Created vector status record for document ID {document.id}")
            except Exception as status_error:
                log_upload_debug(correlation_id, f"Error creating vector status: {status_error}", status_error)
                raise
            
            logger.info(f"[{correlation_id}] Created document ID {document.id} and vector status in PostgreSQL")
            
        # Initialize PDF processor with correct parameters
        log_upload_debug(correlation_id, f"Initializing PDFProcessor: index={index_name}, vector_db_id={vector_database_id}, mock_mode={mock_mode}")
        processor = PDFProcessor(
            index_name=index_name, 
            namespace=namespace, 
            api_key=api_key, 
            vector_db_id=vector_database_id,
            mock_mode=mock_mode,
            correlation_id=correlation_id
        )
        
        # Send embedding start notification via WebSocket
        if user_id:
            try:
                await send_progress_update(
                user_id, 
                file_id, 
                "embedding_start", 
                0.4, 
                "Starting to process PDF and create embeddings"
            )
                log_upload_debug(correlation_id, f"Sent embedding start notification to user {user_id}")
            except Exception as ws_error:
                log_upload_debug(correlation_id, f"Error sending WebSocket notification: {ws_error}", ws_error)
        
        # Process PDF and create embeddings with progress callback
        log_upload_debug(correlation_id, f"Processing PDF with file_path={temp_file_path}, document_id={file_id}")
        result = await processor.process_pdf(
            file_path=temp_file_path,
            document_id=file_id,
            metadata=metadata,
            progress_callback=send_progress_update if user_id else None
        )
        
        log_upload_debug(correlation_id, f"PDF processing result: {result}")
        
        # Handle PDF processing result
        return await handle_pdf_processing_result(result, correlation_id, user_id, file_id, file.filename, document, vector_status, 
                                                vector_database_id, temp_file_path, db, is_pdf, mock_mode)
    except Exception as e:
        return await handle_upload_error(e, correlation_id, temp_file_path, user_id, file_id, file.filename, vector_database_id, vector_status, db, mock_mode)

# Error handling for upload_pdf function
async def handle_upload_error(e, correlation_id, temp_file_path, user_id, file_id, filename, vector_database_id, vector_status, db, mock_mode):
    """Fixed version of the error handling part with proper indentation"""
    log_upload_debug(correlation_id, f"Error in upload_pdf: {str(e)}", e)
    logger.exception(f"[{correlation_id}] Error in upload_pdf: {str(e)}")
    
    # Cleanup on error
    if os.path.exists(temp_file_path):
        try:
            os.remove(temp_file_path)
            log_upload_debug(correlation_id, f"Cleaned up temp file after error: {temp_file_path}")
        except Exception as cleanup_error:
            log_upload_debug(correlation_id, f"Error cleaning up temporary file: {cleanup_error}", cleanup_error)
        
    # Update error status in PostgreSQL
    if vector_database_id and vector_status:
        try:
            vector_status.status = "failed"
            vector_status.error_message = str(e)
            db.commit()
            log_upload_debug(correlation_id, f"Updated database with error status")
        except Exception as db_error:
            log_upload_debug(correlation_id, f"Error updating database with error status: {db_error}", db_error)
        
    # Send failure notification via WebSocket
    if user_id and file_id:
        try:
            await send_pdf_upload_failed(
                user_id,
                file_id,
                filename,
                str(e)
            )
            log_upload_debug(correlation_id, f"Sent failure notification for exception")
        except Exception as ws_error:
            log_upload_debug(correlation_id, f"Error sending WebSocket notification for failure: {ws_error}", ws_error)
            
    log_upload_debug(correlation_id, f"Upload request failed with exception: {str(e)}")
    return PDFResponse(
        success=False,
        error=str(e),
        mock_mode=mock_mode
    )

# Endpoint xóa tài liệu
@router.delete("/namespace", response_model=PDFResponse)
async def delete_namespace(
    namespace: str = "Default",
    index_name: str = "testbot768",
    vector_database_id: Optional[int] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Xóa toàn bộ embeddings trong một namespace từ Pinecone (tương ứng xoá namespace)

    - **namespace**: Namespace trong Pinecone (mặc định: "Default")
    - **index_name**: Tên index Pinecone (mặc định: "testbot768")
    - **vector_database_id**: ID của vector database trong PostgreSQL (nếu có)
    - **user_id**: ID của người dùng để cập nhật trạng thái qua WebSocket
    """
    logger.info(f"Delete namespace request: namespace={namespace}, index={index_name}, vector_db_id={vector_database_id}")
    
    try:
        # Nếu có vector_database_id, lấy thông tin từ PostgreSQL
        api_key = None
        vector_db = None
        mock_mode = False  # Use real mode by default

        if vector_database_id:
            vector_db = db.query(VectorDatabase).filter(
                VectorDatabase.id == vector_database_id,
                VectorDatabase.status == "active"
            ).first()
            if not vector_db:
                return PDFResponse(
                    success=False,
                    error=f"Vector database with ID {vector_database_id} not found or inactive"
                )
            
            # Use index from vector database
            index_name = vector_db.pinecone_index
            
            # Get API key
            if hasattr(vector_db, 'api_key_ref') and vector_db.api_key_ref:
                api_key = vector_db.api_key_ref.key_value
            elif hasattr(vector_db, 'api_key') and vector_db.api_key:
                api_key = vector_db.api_key
            
            # Use namespace based on vector database ID
            namespace = f"vdb-{vector_database_id}" if vector_database_id else namespace
            logger.info(f"Using namespace '{namespace}' based on vector database ID")
            
        # Gửi thông báo bắt đầu xóa qua WebSocket
        if user_id:
            await send_pdf_delete_started(user_id, namespace)
            
        processor = PDFProcessor(
            index_name=index_name, 
            namespace=namespace,
            api_key=api_key,
            vector_db_id=vector_database_id,
            mock_mode=mock_mode
        )
        result = await processor.delete_namespace()
        
        # If in mock mode, also update PostgreSQL to reflect the deletion
        if mock_mode and result.get('success') and vector_database_id:
            try:
                # Update vector statuses for this database
                affected_count = db.query(VectorStatus).filter(
                    VectorStatus.vector_database_id == vector_database_id,
                    VectorStatus.status != "deleted"
                ).update({"status": "deleted", "updated_at": datetime.now()})
                
                # Update document embedding status
                db.query(Document).filter(
                    Document.vector_database_id == vector_database_id,
                    Document.is_embedded == True
                ).update({"is_embedded": False})
                
                db.commit()
                logger.info(f"Updated {affected_count} vector statuses to 'deleted'")
                
                # Include this info in the result
                result["updated_records"] = affected_count
            except Exception as db_error:
                logger.error(f"Error updating PostgreSQL records after namespace deletion: {db_error}")
                result["postgresql_update_error"] = str(db_error)
        
        # Gửi thông báo kết quả qua WebSocket
        if user_id:
            if result.get('success'):
                await send_pdf_delete_completed(user_id, namespace)
            else:
                await send_pdf_delete_failed(user_id, namespace, result.get('error', 'Unknown error'))
                
        return result
    except Exception as e:
        logger.exception(f"Error in delete_namespace: {str(e)}")
        
        # Gửi thông báo lỗi qua WebSocket
        if user_id:
            await send_pdf_delete_failed(user_id, namespace, str(e))
            
        return PDFResponse(
            success=False,
            error=str(e)
        )

# Endpoint lấy danh sách tài liệu
@router.get("/documents", response_model=DocumentsListResponse)
async def get_documents(
    namespace: str = "Default", 
    index_name: str = "testbot768",
    vector_database_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Lấy thông tin về tất cả tài liệu đã được embed
    
    - **namespace**: Namespace trong Pinecone (mặc định: "Default")
    - **index_name**: Tên index Pinecone (mặc định: "testbot768")
    - **vector_database_id**: ID của vector database trong PostgreSQL (nếu có)
    """
    logger.info(f"Get documents request: namespace={namespace}, index={index_name}, vector_db_id={vector_database_id}")
    
    try:
        # Nếu có vector_database_id, lấy thông tin từ PostgreSQL
        api_key = None
        vector_db = None
        mock_mode = False  # Use real mode by default

        if vector_database_id:
            vector_db = db.query(VectorDatabase).filter(
                VectorDatabase.id == vector_database_id,
                VectorDatabase.status == "active"
            ).first()
            
            if not vector_db:
                return DocumentsListResponse(
                    success=False,
                    error=f"Vector database with ID {vector_database_id} not found or inactive"
                )
                
            # Use index from vector database
            index_name = vector_db.pinecone_index
            
            # Get API key
            if hasattr(vector_db, 'api_key_ref') and vector_db.api_key_ref:
                api_key = vector_db.api_key_ref.key_value
            elif hasattr(vector_db, 'api_key') and vector_db.api_key:
                api_key = vector_db.api_key
                
            # Use namespace based on vector database ID
            namespace = f"vdb-{vector_database_id}" if vector_database_id else namespace
            logger.info(f"Using namespace '{namespace}' based on vector database ID")
            
        # Khởi tạo PDF processor
        processor = PDFProcessor(
            index_name=index_name, 
            namespace=namespace,
            api_key=api_key,
            vector_db_id=vector_database_id,
            mock_mode=mock_mode
        )
        
        # Lấy danh sách documents từ Pinecone
        pinecone_result = await processor.list_documents()
        
        # If vector_database_id is provided, also fetch from PostgreSQL
        if vector_database_id:
            try:
                # Get all successfully embedded documents for this vector database
                documents = db.query(Document).join(
                    VectorStatus, Document.id == VectorStatus.document_id
                ).filter(
                    Document.vector_database_id == vector_database_id,
                    Document.is_embedded == True,
                    VectorStatus.status == "completed"
                ).all()
                
                # Add document info to the result
                if documents:
                    pinecone_result["postgresql_documents"] = [
                        {
                            "id": doc.id,
                            "name": doc.name,
                            "file_type": doc.file_type,
                            "content_type": doc.content_type,
                            "created_at": doc.created_at.isoformat() if doc.created_at else None
                        }
                        for doc in documents
                    ]
                    pinecone_result["postgresql_document_count"] = len(documents)
            except Exception as db_error:
                logger.error(f"Error fetching PostgreSQL documents: {db_error}")
                pinecone_result["postgresql_error"] = str(db_error)
        
        return pinecone_result
    except Exception as e:
        logger.exception(f"Error in get_documents: {str(e)}")
        
        return DocumentsListResponse(
            success=False,
            error=str(e)
        ) 

# Health check endpoint for PDF API
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "message": "PDF API is running"
    }

# Document deletion endpoint
@router.delete("/document", response_model=PDFResponse)
async def delete_document(
    document_id: str,
    namespace: str = "Default",
    index_name: str = "testbot768",
    vector_database_id: Optional[int] = None,
    user_id: Optional[str] = None,
    mock_mode: bool = False,
    db: Session = Depends(get_db)
):
    """
    Delete vectors for a specific document from the vector database
    
    - **document_id**: ID of the document to delete
    - **namespace**: Namespace in the vector database (default: "Default")
    - **index_name**: Name of the vector index (default: "testbot768")
    - **vector_database_id**: ID of vector database in PostgreSQL (optional)
    - **user_id**: User ID for WebSocket status updates (optional)
    - **mock_mode**: Simulate vector database operations (default: false)
    """
    logger.info(f"Delete document request: document_id={document_id}, namespace={namespace}, index={index_name}, vector_db_id={vector_database_id}, mock_mode={mock_mode}")
    
    try:
        # If vector_database_id is provided, get info from PostgreSQL
        api_key = None
        vector_db = None

        if vector_database_id:
            vector_db = db.query(VectorDatabase).filter(
                VectorDatabase.id == vector_database_id,
                VectorDatabase.status == "active"
            ).first()
            if not vector_db:
                return PDFResponse(
                    success=False,
                    error=f"Vector database with ID {vector_database_id} not found or inactive"
                )
            
            # Use index from vector database
            index_name = vector_db.pinecone_index
            
            # Get API key
            if hasattr(vector_db, 'api_key_ref') and vector_db.api_key_ref:
                api_key = vector_db.api_key_ref.key_value
            elif hasattr(vector_db, 'api_key') and vector_db.api_key:
                api_key = vector_db.api_key
            
            # Use namespace based on vector database ID
            namespace = f"vdb-{vector_database_id}" if vector_database_id else namespace
            logger.info(f"Using namespace '{namespace}' based on vector database ID")
            
        # Send notification of deletion start via WebSocket if user_id provided
        if user_id:
            try:
                await send_pdf_delete_started(user_id, document_id)
            except Exception as ws_error:
                logger.error(f"Error sending WebSocket notification: {ws_error}")
        
        # Initialize PDF processor
        processor = PDFProcessor(
            index_name=index_name, 
            namespace=namespace, 
            api_key=api_key, 
            vector_db_id=vector_database_id,
            mock_mode=mock_mode
        )
        
        # Delete document vectors
        result = await processor.delete_document(document_id)
        
        # If successful and vector_database_id is provided, update PostgreSQL records
        if result.get('success') and vector_database_id:
            try:
                # Find document by vector ID if it exists
                document = db.query(Document).join(
                    VectorStatus, Document.id == VectorStatus.document_id
                ).filter(
                    Document.vector_database_id == vector_database_id,
                    VectorStatus.vector_id == document_id
                ).first()
                
                if document:
                    # Update vector status
                    vector_status = db.query(VectorStatus).filter(
                        VectorStatus.document_id == document.id,
                        VectorStatus.vector_database_id == vector_database_id
                    ).first()
                    
                    if vector_status:
                        vector_status.status = "deleted"
                        db.commit()
                        result["postgresql_updated"] = True
                        logger.info(f"Updated vector status for document ID {document.id} to 'deleted'")
            except Exception as db_error:
                logger.error(f"Error updating PostgreSQL records: {db_error}")
                result["postgresql_error"] = str(db_error)
        
        # Send notification of deletion completion via WebSocket if user_id provided
        if user_id:
            try:
                if result.get('success'):
                    await send_pdf_delete_completed(user_id, document_id)
                else:
                    await send_pdf_delete_failed(user_id, document_id, result.get('error', 'Unknown error'))
            except Exception as ws_error:
                logger.error(f"Error sending WebSocket notification: {ws_error}")
        
        return result
    except Exception as e:
        logger.exception(f"Error in delete_document: {str(e)}")
        
        # Send notification of deletion failure via WebSocket if user_id provided
        if user_id:
            try:
                await send_pdf_delete_failed(user_id, document_id, str(e))
            except Exception as ws_error:
                logger.error(f"Error sending WebSocket notification: {ws_error}")
        
        return PDFResponse(
            success=False,
            error=str(e),
            mock_mode=mock_mode
        )



