from fastapi import HTTPException, Depends, APIRouter, BackgroundTasks
# from routers import router
from models import Comment, Review, Session, get_db, Post, Project
# from schemas.FeedbackSchema import FeedbackSchema
# from schemas.LearningReviewSchema import LearningReviewSchema
from schemas.Feedback import ( GenerateFeedbackRequest, GenerateFeedbackResponse, FeedbackDetailResponse, RateFeedbackRequest)
from services.process_feedback import process_feedback
from datetime import datetime
from sqlalchemy.orm import Session as ORMSession
from utils.redis_utils import Redis
import uuid



router = APIRouter()

@router.get("/feedback/status/{task_id}")
async def get_feedback_status(task_id: str):
    data = Redis.read_dict(f"feedback:{task_id}")

    if not data:
        return {"status": "pending", "result": None}

    return data

@router.post("/feedback/generate", response_model=GenerateFeedbackResponse)
async def generate_feedback(
    req: GenerateFeedbackRequest,
    background_tasks: BackgroundTasks,
    db: ORMSession = Depends(get_db)
):
    """
    生成回饋
    """
    # 檢查是否有對應的 review
    review = db.query(Review).filter(Review.id == req.reviewId).first()
    if not review:
        raise HTTPException(status_code=404, detail="找不到對應的學習覆盤")

    post = db.query(Post).filter(Post.id == review.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="找不到相關聯的 post")

    project = db.query(Project).filter(Project.id == post.project_id).first()
    
    
    # 組成 context 給 LLM
    context = f"""
    你是一位學習教練，請根據以下使用者輸入內容，給出「個人化」、「實用」、「具體可行」的學習回饋與建議：

    🧠 覆盤回顧內容：
    - 學習心得評分（1-10）：{review.learning_review}
    - 覆盤內容：{review.learning_feedback}
    - 調整與規劃：{review.adjustment_plan}
    - 心情狀態：{review.mood}（說明：{review.mood_description}）
    - 壓力等級（1-10）：{review.stress_level}

    📘 專案資訊：
    - 專案標題：{project.title if project else '未知'}
    - 專案描述：{project.description if project else '未知'}
    - 專案目標：{project.goal if project and project.goal else '未提供'}
    - 動機說明：{project.motivation_description if project and project.motivation_description else '未提供'}
    - 策略說明：{project.strategy_description if project and project.strategy_description else '未提供'}
    - 預期成果說明：{project.outcome_description if project and project.outcome_description else '未提供'}
    - 專案狀態：{project.status if project else '未知'}
    - 起訖日期：{project.start_date} ~ {project.end_date}（週期：{project.interval} 天）

    📝 本週貼文資訊：
    - 標題：{post.title}
    - 週次：{post.week}
    - 日期：{post.date}

    請回覆給使用者一段清楚、貼心、專屬的建議與鼓勵。
    """
    


    # 背景產生回饋（以 review 為 context）
    # background_tasks.add_task(process_feedback, context)
    # 建立唯一任務 ID
    task_id = str(uuid.uuid4())
    
    background_tasks.add_task(process_feedback, context, task_id)

    return GenerateFeedbackResponse(
        feedbackId=task_id,
        content="已提交生成任務，請稍後查看",
        # generatedAt=comment.created_at
    )

@router.get("/feedback/{review_id}", response_model=FeedbackDetailResponse)
async def get_feedback(review_id: int, db: ORMSession = Depends(get_db)):
    """
    取得回饋
    """
    review = db.query(Review).filter(Review.id == review_id).first()
    feedback = db.query(Comment).filter(Comment.target_id == review_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="找不到對應的回饋留言")

    return FeedbackDetailResponse(
        feedbackId=feedback.id,
        reviewId=review.id,
        style=feedback.style,
        thinkingMethod=feedback.thinking_method,
        content=feedback.content,
        tokenUsage=feedback.token_usage,
        createdAt=feedback.created_at
    )


@router.put("/feedback/{feedback_id}/rate")
async def rate_feedback(
    feedback_id: int,
    req: RateFeedbackRequest,
    db: ORMSession = Depends(get_db)
):
    """
    評價回饋
    """
    feedback = db.query(Comment).filter(Comment.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="找不到對應的回饋留言")

    if not (1 <= req.rating <= 5):
        raise HTTPException(status_code=400, detail="評分需介於 1 到 5 之間")

    # 實際可儲存至 `rating` 欄位
    feedback.rating = req.rating
    db.commit()
    return {"message": "評分成功"}


