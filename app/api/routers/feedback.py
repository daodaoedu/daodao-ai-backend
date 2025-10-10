import uuid

from api.schemas.feedback import (
    FeedbackDetailResponse,
    GenerateFeedbackRequest,
    GenerateFeedbackResponse,
)
from core.limiter import limiter  # 從獨立模組 import
from dependencies import CacheDep, LLMDep, SessionDep, UserDep
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from logger import AppLogger
from models import AIReviewFeedback, get_db
from services.feedback import prepare_feedback_context
from services.process_feedback import process_feedback
from sqlalchemy import desc
from sqlalchemy.orm import Session as ORMSession

logger = AppLogger(__name__).get_logger()


# router = APIRouter()
router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


@router.get("/status/{task_id}")
@limiter.limit("60/minute")
async def get_feedback_status(request: Request, task_id: str, cache_client: CacheDep):
    data = cache_client.read_dict(f"feedback:{task_id}")

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
    current_user: UserDep,
    req: GenerateFeedbackRequest,
    background_tasks: BackgroundTasks,
    db: SessionDep,
    llm_client: LLMDep,
):
    """
    生成回饋
    example:
    curl -X 'POST' \
    'http://localhost:8002/api/v1/feedback/generate' \
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
    context = prepare_feedback_context(db, req, llm_client)
    logger.info(f"context {context}")
    logger.info("-" * 36)

    # Generate unique task ID and trigger background processing
    task_id = str(uuid.uuid4())
    background_tasks.add_task(  # TODOS : use celery task
        process_feedback,
        req,
        llm_client,
        context,
        task_id,
        db,
    )

    # 立即回傳 task_id，其他欄位等 status 查詢
    return {
        "feedbackId": task_id,
        "content": "已提交生成任務，請稍後查看",
        "tokenUsage": 0,
        "generatedAt": None,
    }


@router.get("/v1/{review_id}", response_model=FeedbackDetailResponse)
@limiter.limit("20/minute")
async def get_feedback(
    request: Request, review_id: int, db: ORMSession = Depends(get_db)
):
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
