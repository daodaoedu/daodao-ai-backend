from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models import Outcome, Post, Review
from src.schemas.feedback import GenerateFeedbackRequest
from src.services.milestone import get_milestones_data
from src.services.project import get_project_data
from src.services.prompts.prompts import RAGPromptBuilder
from src.services.review import get_review_trends
from src.services.task import get_tasks_stats


def prepare_feedback_context(db: Session, req: GenerateFeedbackRequest) -> str:
    """Prepare comprehensive context for feedback generation"""

    # Get review and related data
    review = db.query(Review).filter(Review.id == req.reviewId).first()
    if not review:
        raise HTTPException(status_code=404, detail="找不到對應的學習覆盤")

    post = db.query(Post).filter(Post.id == review.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="找不到相關聯的 post")

    # Get project and related data
    project = get_project_data(db, post.project_id)
    milestones = get_milestones_data(db, post.project_id)
    tasks_stats_dict = get_tasks_stats(db, [m.id for m in milestones])
    review_trends = get_review_trends(db, post.project_id, req.reviewId)

    # Format milestone progress
    milestone_status = "\n".join([f"- {m.name}: {m.is_completed}" for m in milestones])

    # Calculate task completion rate
    task_completion_rate = (
        (tasks_stats_dict["completed"] / tasks_stats_dict["total"] * 100)
        if tasks_stats_dict["total"] > 0
        else 0
    )

    # Analyze review trends
    recent_reviews = review_trends[:5]  # Last 5 reviews
    avg_learning_score = (
        sum(r.learning_review for r in recent_reviews) / len(recent_reviews)
        if recent_reviews
        else 0
    )
    avg_stress_level = (
        sum(r.stress_level for r in recent_reviews) / len(recent_reviews)
        if recent_reviews
        else 0
    )

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
            outcome_section += (
                f"  可見性：{o.visibility}  建立：{o.created_at}  更新：{o.updated_at}\n"
            )
    else:
        outcome_section = "\n\n📒 學習成果紀錄：無\n"

    # 教練風格與思考方法說明
    style_str = req.style or "未指定"
    thinking_method_str = req.thinking_method or "未指定"
    style_section = f"\n【指定教練風格】：{style_str}\n【指定思考方法】：{thinking_method_str}\n"

    if outcomes:
        outcome_section = "\n\n📒 學習成果紀錄：\n"
        for o in outcomes:
            outcome_section += f"- 內容：{o.content or '無'}\n"
            if o.image_urls:
                outcome_section += f"  圖片：{', '.join(o.image_urls)}\n"
            if o.video_urls:
                outcome_section += f"  影片：{', '.join(o.video_urls)}\n"
            outcome_section += (
                f"  可見性：{o.visibility}  建立：{o.created_at}  更新：{o.updated_at}\n"
            )
    else:
        outcome_section = "\n\n📒 學習成果紀錄：無\n"

    # 教練風格與思考方法說明
    style_str = req.style or "未指定"
    thinking_method_str = req.thinking_method or "未指定"
    style_section = f"\n【指定教練風格】：{style_str}\n【指定思考方法】：{thinking_method_str}\n"

    builder = RAGPromptBuilder()
    prompt = builder.create_rag_prompt(
        style_section=style_section,
        review=review,
        avg_learning_score=avg_learning_score,
        avg_stress_level=avg_stress_level,
        project=project,
        task_completion_rate=task_completion_rate,
        milestone_status=milestone_status,
        post=post,
        outcome_section=outcome_section,
    )

    return prompt
