from fastapi import HTTPException, Depends, APIRouter, BackgroundTasks
from models import get_db,  AIReviewFeedback
from schemas.Feedback import ( GenerateFeedbackRequest, GenerateFeedbackResponse, FeedbackDetailResponse)
from services.process_feedback import process_feedback
from services.feedback import prepare_feedback_context
from sqlalchemy.orm import Session as ORMSession
from utils.redis_utils import Redis
import uuid



# router = APIRouter()
router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("/status/{task_id}")
async def get_feedback_status(task_id: str):
    data = Redis.read_dict(f"feedback:{task_id}")

    if not data or data.get("status") != "done":
        return {"status": "pending", "result": None}

    # 只回傳指定欄位
    return {
        "feedbackId": data.get("feedbackId"),
        "content": data.get("content"),
        "tokenUsage": data.get("tokenUsage"),
        "generatedAt": data.get("generatedAt")
    }

@router.post("/generate", response_model=GenerateFeedbackResponse)
async def generate_feedback(
    req: GenerateFeedbackRequest,
    background_tasks: BackgroundTasks,
    db: ORMSession = Depends(get_db)
):
    """
    生成回饋
    """
    # Prepare comprehensive context for feedback
    context = prepare_feedback_context(db, req.reviewId, req.style, req.thinkingMethod)
    print(f"context {context}")
    print("-"*36)

    # Generate unique task ID and trigger background processing
    task_id = str(uuid.uuid4())
    background_tasks.add_task(process_feedback, req.style, req.thinkingMethod, context, task_id, req.reviewId , db)

    # 立即回傳 task_id，其他欄位等 status 查詢
    return {
        "feedbackId": task_id,
        "content": "已提交生成任務，請稍後查看",
        "tokenUsage": 0,
        "generatedAt": None
    }

@router.get("/{review_id}", response_model=FeedbackDetailResponse)
async def get_feedback(review_id: int, db: ORMSession = Depends(get_db)):
    """
    取得回饋
    """
    ai_feedback = db.query(AIReviewFeedback).filter(AIReviewFeedback.review_id == review_id).first()

    if not ai_feedback:
        raise HTTPException(status_code=404, detail="找不到對應的回饋留言")

    return FeedbackDetailResponse(
        feedbackId=ai_feedback.id,
        reviewId=ai_feedback.review_id,
        style=ai_feedback.style,
        thinkingMethod=ai_feedback.thinking_method,
        content=ai_feedback.content,
        tokenUsage=ai_feedback.token_usage,
        createdAt=ai_feedback.created_at
    )
