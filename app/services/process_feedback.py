from services.generate_feedback import generate_feedback
from utils.llm_router import query_openai, query_gemini, query_grok
from models import Comment, Session
from utils.redis_utils import Redis
from datetime import datetime

def process_feedback(context: str, task_id: str):
    """
    背景任務：產生回饋並儲存至 Redis
    """
    try:
        # output: str, cost: float, usage: dict
        output, cost, usage = query_openai(context)
        token_usage = round(cost, 6)
        generated_at = datetime.now().isoformat()

        # 儲存至 Redis
        Redis.write_dict(f"feedback:{task_id}", {
            "status": "done",
            "feedbackId": task_id,
            "content": output,
            "tokenUsage": token_usage,
            "generatedAt": generated_at
        })

    except Exception as e:
        Redis.write_dict(f"feedback:{task_id}", {
            "status": "error",
            "message": str(e)
        })
