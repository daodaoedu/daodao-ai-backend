from models import Reivew

@app.post("/learning_review")
async def update_learning_review(review: Reivew):
    # 1. 儲存使用者覆盤到資料庫 (此處略過實際資料庫操作)
    
    # 2. 根據 user_id 查詢相關學習資料並聚合成 context (範例)
    context = f"使用者基本資料、學習計畫、里程碑、任務、學習成果、便利貼、覆盤內容：{review.content}"
    
    # 3. 取得回饋建議
    try:
        feedback = generate_feedback(context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成回饋失敗：{str(e)}")
    
    # 4. 將回饋存入資料庫 (此處略過實際資料庫操作)
    
    return {"status": "success", "feedback": feedback}