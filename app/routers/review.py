from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
from pydantic import BaseModel

from services.review_service import ReviewService

router = APIRouter(
    prefix="/review",
    tags=["review"]
)

review_service = ReviewService()

class ReviewRequest(BaseModel):
    user_data: Dict
    history_data: List[Dict]
    review_type: Optional[str] = None

class ProgressAnalysisRequest(BaseModel):
    user_data: Dict
    history_data: List[Dict]
    specific_aspects: Optional[List[str]] = None

@router.post("/generate")
async def generate_review(request: ReviewRequest):
    """生成個人化的回饋與建議"""
    try:
        result = review_service.generate_review(
            request.user_data,
            request.history_data,
            request.review_type
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze-progress")
async def analyze_progress(request: ProgressAnalysisRequest):
    """分析使用者的進步情況"""
    try:
        result = review_service.analyze_progress(
            request.user_data,
            request.history_data,
            request.specific_aspects
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
