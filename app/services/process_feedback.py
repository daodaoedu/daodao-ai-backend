from services.generate_feedback import generate_feedback
from utils.llm_router import query_openai, query_gemini, query_grok
from models import Comment, Session, AIReviewFeedback, Review
from utils.redis_utils import Redis
from datetime import datetime
from sqlalchemy.orm import Session as ORMSession
from fastapi import HTTPException

def process_feedback(style, thinking_method, context: str, task_id: str, review_id: int, db: ORMSession):
    """
    背景任務：產生回饋並儲存至 Redis 和資料庫
    """
    try:
        # output: str, cost: float, usage: dict
        output, cost, usage = query_openai(context)
        token_usage = round(cost, 6)
        generated_at = datetime.now().isoformat()

        # 儲存至資料庫
        ai_feedback = AIReviewFeedback(
            review_id=review_id,
            task_id=task_id,
            content=output,
            token_usage=token_usage,
            created_at=generated_at,
            style=style,
            thinking_method=thinking_method,
        )
        print(f"output, cost, usage {output}, {cost}, {usage},task_id {task_id} ")
        db.add(ai_feedback)
        db.commit()

        # 儲存至 Redis
        Redis.write_dict(f"feedback:{task_id}", {
            "status": "done",
            "feedbackId": task_id,
            "content": output,
            "tokenUsage": token_usage,
            "generatedAt": generated_at
        })

    except Exception as e:
        if 'db' in locals():
            db.rollback()
        Redis.write_dict(f"feedback:{task_id}", {
            "status": "error",
            "message": str(e)
        })
