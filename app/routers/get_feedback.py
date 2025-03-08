from routers import router
from models import Comment, Session, get_db
from schemas import FeedbackSchema
from fastapi import HTTPException, Depends


@router.get("/learning_review/{review_id}/feedback", response_model=FeedbackSchema)
async def get_feedback(review_id: int, db: Session = Depends(get_db)):
    """
    根據覆盤 ID 查詢自動生成的回饋留言
    """
    feedback = db.query(Comment).filter(Comment.review_id == review_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="找不到對應的回饋留言")
    return feedback