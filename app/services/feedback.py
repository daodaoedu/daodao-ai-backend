from fastapi import HTTPException
from models import Outcome, Post, Review
from sqlalchemy.orm import Session

from .milestone import get_milestones_data
from .project import get_project_data
from .review import get_review_trends
from .task import get_tasks_stats


def prepare_feedback_context(
    db: Session, review_id: int, style: str = None, thinking_method: str = None
) -> str:
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
    milestones = get_milestones_data(db, post.project_id)
    tasks_stats_dict = get_tasks_stats(db, [m.id for m in milestones])
    review_trends = get_review_trends(db, post.project_id, review_id)

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
    style_str = style or "未指定"
    thinking_method_str = thinking_method or "未指定"
    style_section = f"\n【指定教練風格】：{style_str}\n【指定思考方法】：{thinking_method_str}\n"

    # Build final context
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
