from fastapi import HTTPException, Depends, APIRouter, BackgroundTasks
# from routers import router
from models import Comment, Review, Session, get_db
from schemas.FeedbackSchema import FeedbackSchema
from schemas.LearningReviewSchema import LearningReviewSchema
from services import process_feedback


router = APIRouter()


@router.get("/feedback/{review_id}", response_model=FeedbackSchema)
async def get_feedback(review_id: int, db: Session = Depends(get_db)):
    """
    根據覆盤 ID 查詢自動生成的回饋留言
    """
    feedback = db.query(Comment).filter(Comment.review_id == review_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="找不到對應的回饋留言")
    return feedback


@router.post("/feedback", response_model=LearningReviewSchema)
async def create_feedback(
    review: LearningReviewSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    新增使用者學習覆盤：
    1. 儲存覆盤資料至資料庫
    2. 根據使用者相關資料聚合 context (此處以覆盤內容示範，實際可擴充其他資料)
    3. 以背景任務呼叫 ChatGPT API 生成回饋留言
    """
    # 儲存學習覆盤 (可根據需要判斷是新增或更新)
    new_review = Review(user_id=review.user_id, content=review.content)
    db.add(new_review)
    db.commit()
    db.refresh(new_review)

    # 聚合 context 資料 (根據實際需求整合更多資訊)
    context = f"使用者ID: {review.user_id}，覆盤內容: {review.content}"
    print(context)

    # 使用背景任務生成回饋留言
    background_tasks.add_task(process_feedback, new_review.id, context, db)

    return new_review
