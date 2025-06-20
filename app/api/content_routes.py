from fastapi import APIRouter, HTTPException, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional
from datetime import datetime
from cachetools import TTLCache
import logging

from app.database.postgresql import get_db
from app.database.models import AboutPixity, SolanaSummit, DaNangBucketList

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(
    prefix="/postgres",
    tags=["Content"],
)

# Initialize caches (5 minutes TTL)
about_pixity_cache = TTLCache(maxsize=1, ttl=300)
solana_summit_cache = TTLCache(maxsize=1, ttl=300)
danang_bucket_list_cache = TTLCache(maxsize=1, ttl=300)

# About Pixity endpoints
@router.get("/about-pixity")
async def get_about_pixity(
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """Get the About Pixity information."""
    try:
        # Check cache first
        if use_cache:
            cached_result = about_pixity_cache.get("about_pixity")
            if cached_result:
                logger.info("Cache hit for about_pixity")
                return cached_result

        # Get or create about pixity content
        about = db.query(AboutPixity).first()
        if not about:
            about = AboutPixity(
                content="Welcome to Pixity",
            )
            db.add(about)
            db.commit()
            db.refresh(about)

        # Cache the result
        if use_cache:
            about_pixity_cache["about_pixity"] = about

        return about
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_about_pixity: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/about-pixity")
async def update_about_pixity(
    content: dict = Body(...),
    db: Session = Depends(get_db)
):
    """Update the About Pixity information."""
    try:
        about = db.query(AboutPixity).first()
        if not about:
            about = AboutPixity(content=content["content"])
            db.add(about)
        else:
            about.content = content["content"]
            about.updated_at = datetime.now()

        db.commit()
        db.refresh(about)

        # Clear cache
        about_pixity_cache.clear()

        return about
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in update_about_pixity: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Solana Summit endpoints
@router.get("/solana-summit")
async def get_solana_summit(
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """Get the Solana Summit information."""
    try:
        # Check cache first
        if use_cache:
            cached_result = solana_summit_cache.get("solana_summit")
            if cached_result:
                logger.info("Cache hit for solana_summit")
                return cached_result

        # Get or create solana summit content
        summit = db.query(SolanaSummit).first()
        if not summit:
            summit = SolanaSummit(
                content="Welcome to Solana Summit",
            )
            db.add(summit)
            db.commit()
            db.refresh(summit)

        # Cache the result
        if use_cache:
            solana_summit_cache["solana_summit"] = summit

        return summit
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_solana_summit: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/solana-summit")
async def update_solana_summit(
    content: dict = Body(...),
    db: Session = Depends(get_db)
):
    """Update the Solana Summit information."""
    try:
        summit = db.query(SolanaSummit).first()
        if not summit:
            summit = SolanaSummit(content=content["content"])
            db.add(summit)
        else:
            summit.content = content["content"]
            summit.updated_at = datetime.now()

        db.commit()
        db.refresh(summit)

        # Clear cache
        solana_summit_cache.clear()

        return summit
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in update_solana_summit: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Da Nang Bucket List endpoints
@router.get("/danang-bucket-list")
async def get_danang_bucket_list(
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """Get the Da Nang Bucket List information."""
    try:
        # Check cache first
        if use_cache:
            cached_result = danang_bucket_list_cache.get("danang_bucket_list")
            if cached_result:
                logger.info("Cache hit for danang_bucket_list")
                return cached_result

        # Get or create bucket list content
        bucket_list = db.query(DaNangBucketList).first()
        if not bucket_list:
            bucket_list = DaNangBucketList(
                content="Da Nang Bucket List",
            )
            db.add(bucket_list)
            db.commit()
            db.refresh(bucket_list)

        # Cache the result
        if use_cache:
            danang_bucket_list_cache["danang_bucket_list"] = bucket_list

        return bucket_list
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_danang_bucket_list: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/danang-bucket-list")
async def update_danang_bucket_list(
    content: dict = Body(...),
    db: Session = Depends(get_db)
):
    """Update the Da Nang Bucket List information."""
    try:
        bucket_list = db.query(DaNangBucketList).first()
        if not bucket_list:
            bucket_list = DaNangBucketList(content=content["content"])
            db.add(bucket_list)
        else:
            bucket_list.content = content["content"]
            bucket_list.updated_at = datetime.now()

        db.commit()
        db.refresh(bucket_list)

        # Clear cache
        danang_bucket_list_cache.clear()

        return bucket_list
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in update_danang_bucket_list: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 