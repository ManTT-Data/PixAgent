@router.get("/danang-bucket-list", response_model=List[DaNangBucketListResponse])
async def get_danang_bucket_list(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """Get all Da Nang Bucket List content items."""
    try:
        cache_key = f"danang_bucket_list_{skip}_{limit}_{active_only}"
        
        if use_cache:
            cached_result = danang_bucket_list_cache.get(cache_key)
            if cached_result:
                return cached_result
        
        query = db.query(DaNangBucketList)
        
        if active_only:
            query = query.filter(DaNangBucketList.is_active == True)
        
        items = query.offset(skip).limit(limit).all()
        result = [DaNangBucketListResponse.model_validate(item, from_attributes=True) for item in items]
        
        if use_cache:
            danang_bucket_list_cache[cache_key] = result
            
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_danang_bucket_list: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/danang-bucket-list", response_model=DaNangBucketListResponse)
async def create_danang_bucket_list(
    bucket_list: DaNangBucketListCreate,
    db: Session = Depends(get_db)
):
    """Create a new Da Nang Bucket List content item."""
    try:
        db_bucket_list = DaNangBucketList(**bucket_list.model_dump())
        db.add(db_bucket_list)
        db.commit()
        db.refresh(db_bucket_list)
        
        danang_bucket_list_cache.clear()
        
        return DaNangBucketListResponse.model_validate(db_bucket_list, from_attributes=True)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in create_danang_bucket_list: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/danang-bucket-list/{bucket_list_id}", response_model=DaNangBucketListResponse)
async def get_danang_bucket_list_by_id(
    bucket_list_id: int = Path(..., gt=0),
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """Get a single Da Nang Bucket List content item by ID."""
    try:
        cache_key = f"danang_bucket_list_{bucket_list_id}"
        
        if use_cache:
            cached_result = danang_bucket_list_cache.get(cache_key)
            if cached_result:
                return cached_result
        
        bucket_list = db.query(DaNangBucketList).filter(DaNangBucketList.id == bucket_list_id).first()
        if not bucket_list:
            raise HTTPException(status_code=404, detail="Da Nang Bucket List content not found")
        
        result = DaNangBucketListResponse.model_validate(bucket_list, from_attributes=True)
        
        if use_cache:
            danang_bucket_list_cache[cache_key] = result
            
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_danang_bucket_list_by_id: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/danang-bucket-list/{bucket_list_id}", response_model=DaNangBucketListResponse)
async def update_danang_bucket_list(
    bucket_list_id: int = Path(..., gt=0),
    bucket_list: DaNangBucketListUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """Update an existing Da Nang Bucket List content item."""
    try:
        db_bucket_list = db.query(DaNangBucketList).filter(DaNangBucketList.id == bucket_list_id).first()
        if not db_bucket_list:
            raise HTTPException(status_code=404, detail="Da Nang Bucket List content not found")
        
        for key, value in bucket_list.model_dump(exclude_unset=True).items():
            setattr(db_bucket_list, key, value)
            
        db.commit()
        db.refresh(db_bucket_list)
        
        danang_bucket_list_cache.clear()
        
        return DaNangBucketListResponse.model_validate(db_bucket_list, from_attributes=True)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in update_danang_bucket_list: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/danang-bucket-list/{bucket_list_id}", response_model=dict)
async def delete_danang_bucket_list(
    bucket_list_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """Delete a Da Nang Bucket List content item."""
    try:
        db_bucket_list = db.query(DaNangBucketList).filter(DaNangBucketList.id == bucket_list_id).first()
        if not db_bucket_list:
            raise HTTPException(status_code=404, detail="Da Nang Bucket List content not found")
        
        db.delete(db_bucket_list)
        db.commit()
        
        danang_bucket_list_cache.clear()
        
        return {"status": "success", "message": f"Da Nang Bucket List content {bucket_list_id} deleted"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error in delete_danang_bucket_list: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}") 