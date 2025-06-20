from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import json
from fastapi.requests import Request

from app.database.postgresql import get_db
from app.database.models import AdminLog

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)

# Pydantic models
class AdminLogEntry(BaseModel):
    id: str
    timestamp: datetime
    user_id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: str
    ip_address: Optional[str] = None
    status: str
    previous_state: Optional[dict] = None
    new_state: Optional[dict] = None

    class Config:
        from_attributes = True

class AdminLogsResponse(BaseModel):
    logs: List[AdminLogEntry]
    total: int
    page: int
    pages: int

# Utility function to create log entries
async def create_admin_log(
    db: Session,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    details: str,
    request: Request,
    status: str = "success",
    previous_state: Optional[dict] = None,
    new_state: Optional[dict] = None
) -> AdminLog:
    """Create a new admin log entry."""
    try:
        log_entry = AdminLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=request.client.host if request else None,
            status=status,
            previous_state=previous_state,
            new_state=new_state
        )
        
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as e:
        db.rollback()
        # Log the error to a separate error logging system
        print(f"Error creating admin log: {str(e)}")
        # Don't raise the exception - logging should not affect the main operation
        return None

@router.get("/logs", response_model=AdminLogsResponse)
async def get_admin_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    time_range: Optional[str] = Query(None, regex="^(7d|30d|90d)$"),
    action: Optional[str] = Query(None, regex="^(create|read|update|delete)$"),
    resource_type: Optional[str] = None,
    user_id: Optional[str] = None,
    status: Optional[str] = Query(None, regex="^(success|failure)$"),
    search_query: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get admin logs with filtering and pagination.
    """
    try:
        # Base query
        query = db.query(AdminLog)

        # Apply filters
        if time_range:
            days = int(time_range.replace('d', ''))
            start_date = datetime.now() - timedelta(days=days)
            query = query.filter(AdminLog.timestamp >= start_date)

        if action:
            query = query.filter(AdminLog.action == action)

        if resource_type:
            query = query.filter(AdminLog.resource_type == resource_type)

        if user_id:
            query = query.filter(AdminLog.user_id == user_id)

        if status:
            query = query.filter(AdminLog.status == status)

        if search_query:
            search_filter = or_(
                AdminLog.details.ilike(f"%{search_query}%"),
                AdminLog.resource_type.ilike(f"%{search_query}%"),
                AdminLog.user_id.ilike(f"%{search_query}%"),
                AdminLog.resource_id.ilike(f"%{search_query}%")
            )
            query = query.filter(search_filter)

        # Get total count
        total_count = query.count()

        # Calculate pagination
        total_pages = (total_count + limit - 1) // limit
        offset = (page - 1) * limit

        # Get paginated results
        logs = query.order_by(desc(AdminLog.timestamp)).offset(offset).limit(limit).all()

        return AdminLogsResponse(
            logs=[AdminLogEntry.model_validate(log, from_attributes=True) for log in logs],
            total=total_count,
            page=page,
            pages=total_pages
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching admin logs: {str(e)}"
        )

# Example of how to use the logging utility in other routes:
"""
@router.post("/some-resource")
async def create_resource(
    request: Request,
    data: SomeModel,
    db: Session = Depends(get_db)
):
    try:
        # Create the resource
        resource = Resource(**data.dict())
        db.add(resource)
        db.commit()
        db.refresh(resource)

        # Log the action
        await create_admin_log(
            db=db,
            user_id=request.state.user_id,  # Assuming user ID is stored in request state
            action="create",
            resource_type="Resource",
            resource_id=str(resource.id),
            details=f"Created resource: {resource.name}",
            request=request
        )

        return resource
    except Exception as e:
        # Log the failure
        await create_admin_log(
            db=db,
            user_id=request.state.user_id,
            action="create",
            resource_type="Resource",
            resource_id=None,
            details=f"Failed to create resource: {str(e)}",
            request=request,
            status="failure"
        )
        raise
""" 