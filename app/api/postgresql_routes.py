from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, File, Form, UploadFile, Path, Query, Response, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text, func
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import traceback
import uuid
import os
import tempfile
import httpx
import asyncio
from pathlib import Path as pathlib_Path
from pydantic import BaseModel, ConfigDict
from cachetools import TTLCache
import pinecone

from app.database.postgresql import get_db
from app.database.models import (
    FAQItem, EmergencyItem, EventItem, AboutPixity, SolanaSummit, DaNangBucketList,
    ApiKey, VectorDatabase, Document, VectorStatus, TelegramBot, ChatEngine,
    BotEngine, EngineVectorDb, DocumentContent, DatabaseMergeOperation
)
from app.api.models import (
    MergeStatusResponse, MergeProgressResponse, DatabaseMergeRequest,
    FAQResponse, FAQCreate, FAQUpdate, BatchFAQCreate,
    EmergencyResponse, EmergencyCreate, EmergencyUpdate, BatchEmergencyCreate,
    EventResponse, EventCreate, EventUpdate, BatchEventCreate,
    BatchUpdateResult,
    InfoContentResponse, InfoContentUpdate,
    ApiKeyResponse, ApiKeyCreate, ApiKeyUpdate,
    VectorDatabaseResponse, VectorDatabaseCreate, VectorDatabaseUpdate, VectorDatabaseDetailResponse,
    DocumentResponse, DocumentCreate, DocumentUpdate,
    TelegramBotResponse, TelegramBotUpdate,
    ChatEngineResponse, ChatEngineCreate, ChatEngineUpdate,
    BotEngineResponse, BotEngineCreate,
    EngineVectorDbResponse, EngineVectorDbCreate,
    VectorStatusResponse,
    DaNangBucketListResponse
)
from app.utils.pdf_processor import PDFProcessor

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(
    prefix="/postgres",
    tags=["PostgreSQL"],
)

# Initialize caches with 5 minutes TTL
content_cache = TTLCache(maxsize=100, ttl=300)

# --- Documents endpoints ---
@router.get("/documents", response_model=List[DocumentResponse])
async def get_documents(
    skip: int = 0,
    limit: int = 100,
    vector_database_id: Optional[int] = None,
    is_embedded: Optional[bool] = None,
    file_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all documents with optional filtering."""
    try:
        # Build query with joins to get vector database name and embedding status
        query = db.query(
            Document,
            VectorDatabase.name.label('vector_database_name'),
            VectorStatus.status.label('vector_status')
        ).join(
            VectorDatabase, Document.vector_database_id == VectorDatabase.id
        ).outerjoin(
            VectorStatus, Document.id == VectorStatus.document_id
        )
        
        # Apply filters
        if vector_database_id:
            query = query.filter(Document.vector_database_id == vector_database_id)
        if file_type:
            query = query.filter(Document.file_type == file_type)
        if is_embedded is not None:
            if is_embedded:
                query = query.filter(VectorStatus.status == 'embedded')
            else:
                query = query.filter(
                    (VectorStatus.status != 'embedded') | (VectorStatus.status.is_(None))
                )
        
        # Apply pagination
        results = query.offset(skip).limit(limit).all()
        
        # Convert to response format
        documents = []
        for doc, vdb_name, vs_status in results:
            doc_dict = {
                'id': doc.id,
                'name': doc.name,
                'file_type': doc.file_type,
                'content_type': doc.content_type,
                'size': doc.size,
                'created_at': doc.created_at,
                'updated_at': doc.updated_at,
                'vector_database_id': doc.vector_database_id,
                'vector_database_name': vdb_name,
                'is_embedded': vs_status == 'embedded' if vs_status else False
            }
            documents.append(DocumentResponse.model_validate(doc_dict))
        
        return documents
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """Get a single document by ID."""
    try:
        # Query with joins to get complete information
        result = db.query(
            Document,
            VectorDatabase.name.label('vector_database_name'),
            VectorStatus.status.label('vector_status')
        ).join(
            VectorDatabase, Document.vector_database_id == VectorDatabase.id
        ).outerjoin(
            VectorStatus, Document.id == VectorStatus.document_id
        ).filter(Document.id == document_id).first()
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Document with ID {document_id} not found")
        
        doc, vdb_name, vs_status = result
        doc_dict = {
            'id': doc.id,
            'name': doc.name,
            'file_type': doc.file_type,
            'content_type': doc.content_type,
            'size': doc.size,
            'created_at': doc.created_at,
            'updated_at': doc.updated_at,
            'vector_database_id': doc.vector_database_id,
            'vector_database_name': vdb_name,
            'is_embedded': vs_status == 'embedded' if vs_status else False
        }
        
        return DocumentResponse.model_validate(doc_dict)
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving document: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/documents", response_model=DocumentResponse)
async def upload_document(
    name: str = Form(...),
    vector_database_id: int = Form(...),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """
    Upload a document to a specific vector database.
    
    - **name**: Document display name
    - **vector_database_id**: ID of the vector database to associate with
    - **file**: Document file to upload
    """
    try:
        # Check if vector database exists
        vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == vector_database_id).first()
        if not vector_db:
            raise HTTPException(status_code=404, detail=f"Vector database with ID {vector_database_id} not found")
        
        # Read file content
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Empty file provided")
        
        # Determine file type and content type
        filename = file.filename or "unknown"
        file_extension = filename.split('.')[-1].lower() if '.' in filename else 'unknown'
        content_type = file.content_type or 'application/octet-stream'
        
        # Create document record
        document = Document(
            name=name,
            file_type=file_extension,
            content_type=content_type,
            size=len(file_content),
            vector_database_id=vector_database_id
        )
        db.add(document)
        db.flush()  # Get the document ID
        
        # Create document content record
        document_content = DocumentContent(
            document_id=document.id,
            content=file_content
        )
        db.add(document_content)
        
        # Create vector status record
        vector_status = VectorStatus(
            document_id=document.id,
            vector_database_id=vector_database_id,
            status="pending"
        )
        db.add(vector_status)
        
        # Commit all changes
        db.commit()
        db.refresh(document)
        
        # Schedule automatic PDF processing to Pinecone if it's a PDF file
        if file_extension.lower() == 'pdf':
            try:
                pinecone_api_key = os.getenv("PINECONE_API_KEY")
                pinecone_index_name = os.getenv("PINECONE_INDEX_NAME", "testbot768")
                
                if pinecone_api_key:
                    # Schedule PDF processing
                    background_tasks.add_task(
                        process_pdf_to_pinecone,
                        file_content=file_content,
                        filename=filename,
                        document_id=document.id,
                        document_name=document.name,
                        vector_database_id=vector_database_id,
                        pinecone_api_key=pinecone_api_key,
                        pinecone_index_name=pinecone_index_name
                    )
                    logger.info(f"Scheduled automatic PDF processing to Pinecone for document {document.id}")
                else:
                    logger.warning("PINECONE_API_KEY not found in environment variables. Skipping automatic Pinecone upload.")
            except Exception as e:
                logger.error(f"Failed to schedule automatic PDF processing for document {document.id}: {str(e)}")
                # Don't fail the upload if Pinecone scheduling fails
        
        # Return document response with vector database info
        doc_dict = {
            'id': document.id,
            'name': document.name,
            'file_type': document.file_type,
            'content_type': document.content_type,
            'size': document.size,
            'created_at': document.created_at,
            'updated_at': document.updated_at,
            'vector_database_id': document.vector_database_id,
            'vector_database_name': vector_db.name,
            'is_embedded': False  # Always false for new uploads
        }
        
        return DocumentResponse.model_validate(doc_dict)
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error uploading document: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error uploading document: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error uploading document: {str(e)}")

async def process_pdf_to_pinecone(
    file_content: bytes,
    filename: str,
    document_id: int,
    document_name: str,
    vector_database_id: int,
    pinecone_api_key: str,
    pinecone_index_name: str
):
    """
    Background task to process PDF and upload to Pinecone.
    
    Args:
        file_content: PDF file content as bytes
        filename: Original filename
        document_id: Database document ID
        document_name: Display name of the document
        vector_database_id: Vector database ID
        pinecone_api_key: Pinecone API key
        pinecone_index_name: Pinecone index name
    """
    # Create a new database session for this background task
    from app.database.postgresql import SessionLocal
    db = SessionLocal()
    
    temp_file_path = None
    try:
        # Create a temporary file for the PDF content
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        # Initialize PDF processor
        pdf_processor = PDFProcessor(
            pinecone_api_key=pinecone_api_key,
            index_name=pinecone_index_name
        )
        
        # Create metadata for the document
        metadata = {
            "document_id": document_id,
            "document_name": document_name,
            "vector_database_id": vector_database_id,
            "filename": filename
        }
        
        # Process the PDF and upload to Pinecone
        result = pdf_processor.process_pdf(
            pdf_path=temp_file_path,
            metadata=metadata
        )
        
        # Update vector status based on result
        vector_status = db.query(VectorStatus).filter(VectorStatus.document_id == document_id).first()
        if vector_status:
            if result.get('success', False):
                vector_status.status = "embedded"
                vector_status.vector_id = result.get('vector_id', f"doc_{document_id}")
                vector_status.embedded_at = datetime.now()
                vector_status.error_message = None
                logger.info(f"Successfully processed PDF document {document_id} to Pinecone")
            else:
                vector_status.status = "failed"
                vector_status.error_message = result.get('error', 'Unknown error occurred')
                logger.error(f"Failed to process PDF document {document_id}: {vector_status.error_message}")
            
            db.commit()
        
    except Exception as e:
        logger.error(f"Error processing PDF to Pinecone for document {document_id}: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Update vector status to failed
        try:
            vector_status = db.query(VectorStatus).filter(VectorStatus.document_id == document_id).first()
            if vector_status:
                vector_status.status = "failed"
                vector_status.error_message = str(e)
                db.commit()
        except Exception as update_error:
            logger.error(f"Failed to update vector status for document {document_id}: {str(update_error)}")
    
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as cleanup_error:
                logger.error(f"Failed to clean up temporary file {temp_file_path}: {str(cleanup_error)}")
        
        # Close database session
        db.close()

@router.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,
    name: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """Update an existing document."""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"Document with ID {document_id} not found")
        
        # Update name if provided
        if name is not None:
            document.name = name
        
        # Update file content if provided
        if file is not None:
            file_content = await file.read()
            if not file_content:
                raise HTTPException(status_code=400, detail="Empty file provided")
            
            # Update document metadata
            filename = file.filename or "unknown"
            file_extension = filename.split('.')[-1].lower() if '.' in filename else 'unknown'
            document.file_type = file_extension
            document.content_type = file.content_type or 'application/octet-stream'
            document.size = len(file_content)
            document.updated_at = datetime.now()
            
            # Update document content
            document_content = db.query(DocumentContent).filter(DocumentContent.document_id == document_id).first()
            if document_content:
                document_content.content = file_content
            else:
                # Create new content record if it doesn't exist
                document_content = DocumentContent(
                    document_id=document_id,
                    content=file_content
                )
                db.add(document_content)
            
            # Update vector status to pending and clear previous embedding data
            vector_status = db.query(VectorStatus).filter(VectorStatus.document_id == document_id).first()
            if vector_status:
                # Delete old status and create new one to avoid constraint issues
                db.delete(vector_status)
                db.flush()
            
            # Create new vector status
            new_vector_status = VectorStatus(
                document_id=document_id,
                vector_database_id=document.vector_database_id,
                status="pending"
            )
            db.add(new_vector_status)
            db.flush()
            logger.info(f"Created new vector status for document {document_id} with status 'pending'")
            
            # Schedule automatic PDF processing if it's a PDF
            if file_extension.lower() == 'pdf':
                try:
                    pinecone_api_key = os.getenv("PINECONE_API_KEY")
                    pinecone_index_name = os.getenv("PINECONE_INDEX_NAME", "testbot768")
                    
                    if pinecone_api_key:
                        # Schedule PDF processing
                        background_tasks.add_task(
                            process_pdf_to_pinecone,
                            file_content=file_content,
                            filename=filename,
                            document_id=document.id,
                            document_name=document.name,
                            vector_database_id=document.vector_database_id,
                            pinecone_api_key=pinecone_api_key,
                            pinecone_index_name=pinecone_index_name
                        )
                        logger.info(f"Scheduled automatic PDF reprocessing for updated document {document.id}")
                    else:
                        logger.warning("PINECONE_API_KEY not found in environment variables. Skipping automatic Pinecone upload.")
                except Exception as e:
                    logger.error(f"Failed to schedule automatic PDF processing for updated document {document.id}: {str(e)}")
        
        # Commit all changes
        db.commit()
        db.refresh(document)
        
        # Get vector database name and embedding status for response
        vector_db = db.query(VectorDatabase).filter(VectorDatabase.id == document.vector_database_id).first()
        vector_status = db.query(VectorStatus).filter(VectorStatus.document_id == document_id).first()
        
        doc_dict = {
            'id': document.id,
            'name': document.name,
            'file_type': document.file_type,
            'content_type': document.content_type,
            'size': document.size,
            'created_at': document.created_at,
            'updated_at': document.updated_at,
            'vector_database_id': document.vector_database_id,
            'vector_database_name': vector_db.name if vector_db else None,
            'is_embedded': vector_status.status == 'embedded' if vector_status else False
        }
        
        return DocumentResponse.model_validate(doc_dict)
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating document: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating document: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error updating document: {str(e)}")

@router.delete("/documents/{document_id}", response_model=dict)
async def delete_document(
    document_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """Delete a document and its associated content."""
    try:
        # Get document
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"Document with ID {document_id} not found")
        
        # Get vector status to check if we need to delete from Pinecone
        vector_status = db.query(VectorStatus).filter(VectorStatus.document_id == document_id).first()
        
        # Delete from Pinecone if vector_id exists
        pinecone_deleted = False
        if vector_status and vector_status.vector_id:
            try:
                base_url = "http://localhost:8000"
                delete_url = f"{base_url}/pdf/delete/{vector_status.vector_id}"
                
                async with httpx.AsyncClient() as client:
                    response = await client.delete(delete_url)
                    if response.status_code == 200:
                        pinecone_deleted = True
                        logger.info(f"Successfully deleted vector {vector_status.vector_id} from Pinecone")
                    else:
                        logger.warning(f"Failed to delete from Pinecone: {response.text}")
            except Exception as e:
                logger.error(f"Error deleting from Pinecone: {str(e)}")
        else:
            logger.warning(f"No vector_id found for document {document_id}, skipping Pinecone deletion")
        
        # Delete vector status
        db.query(VectorStatus).filter(VectorStatus.document_id == document_id).delete()
        
        # Delete document content
        db.query(DocumentContent).filter(DocumentContent.document_id == document_id).delete()
        
        # Delete document
        db.delete(document)
        db.commit()
        
        # Prepare response with information about what happened
        response = {
            "status": "success", 
            "message": f"Document with ID {document_id} deleted successfully",
            "pinecone_deleted": pinecone_deleted
        }
        
        return response
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting document: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/{document_id}/content", response_class=Response)
async def get_document_content(
    document_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """Get document content for download."""
    try:
        # Get document and its content
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"Document with ID {document_id} not found")
        
        document_content = db.query(DocumentContent).filter(DocumentContent.document_id == document_id).first()
        if not document_content:
            raise HTTPException(status_code=404, detail=f"Content for document {document_id} not found")
        
        # Return file content with appropriate headers
        return Response(
            content=document_content.content,
            media_type=document.content_type or 'application/octet-stream',
            headers={
                "Content-Disposition": f"attachment; filename={document.name}.{document.file_type}"
            }
        )
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving document content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Health check endpoint ---
@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable") 