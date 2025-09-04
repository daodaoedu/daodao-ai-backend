import uuid

from api.schemas.feedback import (
    FeedbackDetailResponse,
    GenerateFeedbackRequest,
    GenerateFeedbackResponse,
)
from api.verify_jwt import get_current_user
from core.limiter import limiter  # 從獨立模組 import
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from logger import AppLogger
from models import AIReviewFeedback, get_db
from services.feedback import prepare_feedback_context
from services.process_feedback import process_feedback
from sqlalchemy import desc
from sqlalchemy.orm import Session as ORMSession
from utils.redis_utils import Redis

logger = AppLogger(__name__).get_logger()


# router = APIRouter()
router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("/status/{task_id}")
@limiter.limit("60/minute")
async def get_feedback_status(request: Request, task_id: str):
    data = Redis.read_dict(f"feedback:{task_id}")

    if not data:
        return {"status": "unknown", "result": None}

    status = data.get("status", "unknown")

    # 若還在 pending / running，content 可選擇不回傳
    if status in ["pending", "running"]:
        return {"status": status, "result": None}

    # 若失敗，回傳錯誤訊息
    if status == "error":
        return {"status": "error", "message": data.get("message")}

    # 若完成
    if status == "done":
        return {
            "status": "done",
            "feedbackId": data.get("feedbackId"),
            "content": data.get("content"),
            "tokenUsage": data.get("tokenUsage"),
            "generatedAt": data.get("generatedAt"),
        }

    return {"status": status, "result": None}


@router.post("/generate", response_model=GenerateFeedbackResponse)
@limiter.limit("5/minute")
async def generate_feedback(
    request: Request, 
    req: GenerateFeedbackRequest,
    background_tasks: BackgroundTasks,
    db: ORMSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # 自動取得驗證後的 payload
):
    """
    生成回饋
    example:
    curl -X 'POST' \
    'http://localhost:8002/api/feedback/generate' \
    -H 'accept: application/json' \
    -H 'Authorization: Bearer <YOUR_TOKEN_ID>' \
    -H 'Content-Type: application/json' \
    -d '{
    "reviewId": 1,
    "style": "string",
    "thinkingMethod": "string"
}'
    """
    # Prepare comprehensive context for feedback
    context = prepare_feedback_context(db, req.reviewId, req.style, req.thinkingMethod)
    logger.info(f"context {context}")
    logger.info("-" * 36)

    # Generate unique task ID and trigger background processing
    task_id = str(uuid.uuid4())
    background_tasks.add_task(
        process_feedback,
        req.style,
        req.thinkingMethod,
        context,
        task_id,
        req.reviewId,
        db,
    )

    # 立即回傳 task_id，其他欄位等 status 查詢
    return {
        "feedbackId": task_id,
        "content": "已提交生成任務，請稍後查看",
        "tokenUsage": 0,
        "generatedAt": None,
    }


@router.get("/{review_id}", response_model=FeedbackDetailResponse)
@limiter.limit("20/minute")
async def get_feedback(request: Request, review_id: int, db: ORMSession = Depends(get_db)):
    """
    取得回饋
    """
    ai_feedback = (
        db.query(AIReviewFeedback)
        .filter(AIReviewFeedback.review_id == review_id)
        .order_by(desc(AIReviewFeedback.created_at))
        .first()
    )

    if not ai_feedback:
        raise HTTPException(status_code=404, detail="找不到對應的回饋留言")

    return FeedbackDetailResponse(
        feedbackId=ai_feedback.id,
        reviewId=ai_feedback.review_id,
        style=ai_feedback.style,
        thinkingMethod=ai_feedback.thinking_method,
        content=ai_feedback.content,
        tokenUsage=ai_feedback.token_usage,
        createdAt=ai_feedback.created_at,
    )
