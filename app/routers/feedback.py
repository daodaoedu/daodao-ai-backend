from fastapi import HTTPException, Depends, APIRouter, BackgroundTasks
# from routers import router
from models import Comment, Review, Session, get_db, Post, Project, Milestone, Task, Outcome
# from schemas.FeedbackSchema import FeedbackSchema
# from schemas.LearningReviewSchema import LearningReviewSchema
from schemas.Feedback import ( GenerateFeedbackRequest, GenerateFeedbackResponse, FeedbackDetailResponse, RateFeedbackRequest)
from services.process_feedback import process_feedback
from datetime import datetime
from sqlalchemy.orm import Session as ORMSession
from sqlalchemy import func, case
from utils.redis_utils import Redis
import uuid



router = APIRouter()

def get_project_data(db: ORMSession, project_id: int):
    """Get and process project data"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="找不到相關專案")
    return project

def get_milestones_data(db: ORMSession, project_id: int):
    """Get and process milestones data"""
    milestones = db.query(Milestone).filter(Milestone.project_id == project_id).all()
    return milestones

def get_tasks_stats(db: ORMSession, milestones: list[Milestone]):
    """Get and process tasks statistics for the given milestones"""
    if not milestones:
        return {'total': 0, 'completed': 0} # Return zero stats if no milestones

    milestone_ids = [m.id for m in milestones]
    print(f" milestone_ids {milestone_ids}")

    tasks_stats = db.query(
        func.count(Task.id).label('total'),
        func.sum(case(
            [(Task.is_completed == True, 1)], # Use is_completed boolean field
            else_=0
        )).label('completed')
    ).filter(Task.milestone_id.in_(milestone_ids)).first() # Filter by milestone_ids

    # Handle case where query returns None (e.g., no tasks found)
    if tasks_stats is None or tasks_stats.total is None:
         return {'total': 0, 'completed': 0}

    # Ensure completed count is not None
    completed_count = tasks_stats.completed if tasks_stats.completed is not None else 0

    return {'total': tasks_stats.total, 'completed': completed_count}

def get_review_trends(db: ORMSession, project_id: int, current_review_id: int):
    """Get review trends for the project"""
    reviews = db.query(Review).join(Post).filter(
        Post.project_id == project_id,
        Review.id <= current_review_id
    ).order_by(Review.created_at.desc()).all()
    return reviews

def prepare_feedback_context(db: ORMSession, review_id: int, style: str = None, thinking_method: str = None):
    """Prepare comprehensive context for feedback generation"""
    # Get review and related data
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="找不到對應的學習覆盤")

    post = db.query(Post).filter(Post.id == review.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="找不到相關聯的 post")

    # Get project and related data

    project = get_project_data(db, post.project_id)
    print(f"檢查並取得專案資料（從快取或重新處理）{project}")
    milestones = get_milestones_data(db, post.project_id)
    print(f"檢查並取得里程碑資料 {milestones}")
    tasks_stats_dict = get_tasks_stats(db, milestones)
    print(f"檢查並取得任務統計資料 {tasks_stats_dict}")
    review_trends = get_review_trends(db, post.project_id, review_id)
    print(f"取得或更新覆盤趨勢資料 (Count: {len(review_trends)})")
    for r in review_trends:
        print(f"Review ID: {r.id}, Learning Score: {r.learning_review}, Stress: {r.stress_level}, Created: {r.created_at}")

    # Format milestone progress
    milestone_status = "\n".join([
        f"- {m.name}: {m.is_completed}" for m in milestones
    ])

    # Calculate task completion rate
    task_completion_rate = (tasks_stats_dict['completed'] / tasks_stats_dict['total'] * 100) if tasks_stats_dict['total'] > 0 else 0

    # Analyze review trends
    recent_reviews = review_trends[:5]  # Last 5 reviews
    avg_learning_score = sum(r.learning_review for r in recent_reviews) / len(recent_reviews) if recent_reviews else 0
    avg_stress_level = sum(r.stress_level for r in recent_reviews) / len(recent_reviews) if recent_reviews else 0

    # 查詢 outcome 資料
    outcomes = db.query(Outcome).filter(Outcome.post_id == post.id).all()
    if outcomes:
        outcome_section = "\n\n📒 學習成果紀錄：\n"
        for o in outcomes:
            outcome_section += f"- 內容：{o.content or '無'}\n"
            if o.image_urls:
                outcome_section += f"  圖片：{', '.join(o.image_urls)}\n"
            if o.video_urls:
                outcome_section += f"  影片：{', '.join(o.video_urls)}\n"
            outcome_section += f"  可見性：{o.visibility}  建立：{o.created_at}  更新：{o.updated_at}\n"
    else:
        outcome_section = "\n\n📒 學習成果紀錄：無\n"

    # 教練風格與思考方法說明
    style_str = style or '未指定'
    thinking_method_str = thinking_method or '未指定'
    style_section = f"\n【指定教練風格】：{style_str}\n【指定思考方法】：{thinking_method_str}\n"

    context = f"""
    {style_section}
    你是一位學習教練，請根據以下使用者輸入內容，給出「個人化」、「實用」、「具體可行」的學習回饋與建議：

    🧠 覆盤回顧內容：
    - 學習心得評分（1-10）：{review.learning_review}
    - 覆盤內容：{review.learning_feedback}
    - 調整與規劃：{review.adjustment_plan}
    - 心情狀態：{review.mood}（說明：{review.mood_description}）
    - 壓力等級（1-10）：{review.stress_level}

    📊 學習趨勢分析：
    - 近期平均學習評分：{avg_learning_score:.1f}
    - 近期平均壓力指數：{avg_stress_level:.1f}

    📘 專案資訊：
    - 專案標題：{project.title}
    - 專案描述：{project.description}
    - 專案目標：{project.goal or '未提供'}
    - 動機說明：{project.motivation_description or '未提供'}
    - 策略說明：{project.strategy_description or '未提供'}
    - 預期成果說明：{project.outcome_description or '未提供'}
    - 專案狀態：{project.status}
    - 起訖日期：{project.start_date} ~ {project.end_date}（週期：{project.interval} 天）

    📈 專案進度：
    - 任務完成率：{task_completion_rate:.1f}%
    里程碑狀態：
    {milestone_status}

    📝 本週貼文資訊：
    - 標題：{post.title}
    - 週次：{post.week}
    - 日期：{post.date}
    {outcome_section}
    請回覆給使用者一段清楚、貼心、專屬的建議與鼓勵。特別注意：
    1. 根據學習趨勢給出針對性建議
    2. 參考專案進度提供實際可行的改進方向
    3. 結合里程碑完成情況給出下一步建議
    """
    return context

@router.get("/feedback/status/{task_id}")
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

@router.post("/feedback/generate", response_model=GenerateFeedbackResponse)
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

    # Generate unique task ID and trigger background processing
    task_id = str(uuid.uuid4())
    background_tasks.add_task(process_feedback, context, task_id)

    # 立即回傳 task_id，其他欄位等 status 查詢
    return {
        "feedbackId": task_id,
        "content": "已提交生成任務，請稍後查看",
        "tokenUsage": 0,
        "generatedAt": None
    }

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
