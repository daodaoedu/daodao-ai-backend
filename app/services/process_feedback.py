from datetime import datetime

from logger import AppLogger
from models import AIReviewFeedback
from sqlalchemy.orm import Session
# from utils.llm_router import query_gemini
from utils.redis_utils import Redis
from services.llm.client import LLMClient
from api.schemas.feedback import GenerateFeedbackRequest

logger = AppLogger(__name__).get_logger()


def pre_process_feedback(llm_client: LLMClient, context: str, wordNum: int = 300,) -> str:
    prompt = f"你是一個專業的摘要生成工具，能夠讀取一段文字並將其精簡成重點，並且保持原始意圖不變。請將以下內容進行摘要，並保持字數在 {wordNum} 字以內：\n\n{context}\n\n請給出精簡的版本。"

    output, cost, usage, llm_name = llm_client.generate(prompt)
    logger.info(
        f"[pre_process_feedback] {llm_name} output: {output}, cost: {cost}, usage: {usage}"
    )
    return output


def process_feedback(
    req: GenerateFeedbackRequest, 
    llm_client: LLMClient,
    context: str, 
    task_id: str, 
    db: Session
):
    """
    背景任務：產生回饋並儲存至 Redis 和資料庫
    """

    # TODO: 處理當前覆盤資料 -> context 太長，做摘要。判斷字數超過300字，則 gemini 進行摘要成300字

    try:
        logger.info(f"feedback:{task_id}, status : pending")
        Redis.write_dict(f"feedback:{task_id}", {"status": "pending"})

        if len(context) > 300:
            context = pre_process_feedback(llm_client=llm_client, context=context, wordNum = 300)
        # output: str, cost: float, usage: dict
        output, cost, usage, llm_name = llm_client.generate(context)
        token_usage = round(usage.get("estimated_tokens"), 6)
        generated_at = datetime.now().isoformat()
        logger.info(f"feedback:{task_id}, status : running")

        Redis.write_dict(f"feedback:{task_id}", {"status": "running"})

        # 儲存至資料庫
        ai_feedback = AIReviewFeedback(
            review_id=req.reviewId,
            task_id=task_id,
            content=output,
            token_usage=token_usage,
            created_at=generated_at,
            style=req.style,
            thinking_method=req.thinking_method,
        )
        db.add(ai_feedback)
        db.commit()
        logger.info(
            f"{llm_name} output, cost, usage {output}, {cost}, {usage},task_id {task_id} "
        )

        # 儲存至 Redis
        Redis.write_dict(
            f"feedback:{task_id}",
            {
                "status": "done",
                "feedbackId": task_id,
                "content": output,
                "tokenUsage": token_usage,
                "generatedAt": generated_at,
            },
        )

    except Exception as e:
        if "db" in locals():
            db.rollback()
        Redis.write_dict(f"feedback:{task_id}", {"status": "error", "message": str(e)})
