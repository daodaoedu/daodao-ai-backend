from services import generate_feedback
from models import Comment, Session

def process_feedback(review_id: int, context: str, db: Session):
    """
    背景任務：產生回饋並儲存到資料庫
    """
    feedback_text = generate_feedback(context)
    feedback_record = Comment(review_id=review_id, content=feedback_text)
    db.add(feedback_record)
    db.commit()
    db.refresh(feedback_record)
    # 這裡可以加入記錄或其他後續處理
