from fastapi import BackgroundTasks, Depends
from models import Reivew
from schemas import LearningReviewSchema
from routers import router, process_feedback
from models import get_db, Session


@router.post("/learning_review", response_model=LearningReviewSchema)
async def create_learning_review(
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
    new_review = Reivew(user_id=review.user_id, content=review.content)
    db.add(new_review)
    db.commit()
    db.refresh(new_review)

    # 聚合 context 資料 (根據實際需求整合更多資訊)
    context = f"使用者ID: {review.user_id}，覆盤內容: {review.content}"
    print(context)
    
    # 使用背景任務生成回饋留言
    background_tasks.add_task(process_feedback, new_review.id, context, db)
    
    return new_review
