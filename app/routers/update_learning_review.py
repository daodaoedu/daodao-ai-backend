from fastapi import HTTPException, Depends, APIRouter, BackgroundTasks
# from models import Review
from schemas.ReviewSchema import ReviewSchema 

from services.generate_feedback import generate_feedback


router = APIRouter()


@router.post("/learning_review", response_model=ReviewSchema)
async def update_learning_review(review: ReviewSchema):
    # 1. 儲存使用者覆盤到資料庫 (此處略過實際資料庫操作)
    
    # 2. 根據 user_id 查詢相關學習資料並聚合成 context (範例)
    context = f"""
    使用者學習覆盤資料：
    - 心情: {review.mood}
    - 壓力等級: {review.stress_level}
    - 學習評價: {review.learning_review}
    - 心情描述: {review.mood_description if review.mood_description else '無'}
    - 學習回饋: {review.learning_feedback if review.learning_feedback else '無'}
    - 調整計劃: {review.adjustment_plan if review.adjustment_plan else '無'}
    - 可見性: {review.visibility}
    """
    
    # 3. 取得回饋建議
    try:
        print(f"正在生成回饋，context: {context} ")

        feedback = generate_feedback(context)
        print(f"回饋: {feedback}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成回饋失敗：{str(e)}")
    
    # 4. 將回饋存入資料庫 (此處略過實際資料庫操作)
    response_data = {
        "status": "success",
        "learning_feedback": feedback,
        "post_id": 123,  # 假設的 post_id
        "mood": "happy",  # 假設的心情
        "stress_level": 5,  # 假設的壓力等級
        "learning_review": review.learning_review  # 假設的學習回顧內容
    }
    
    return response_data