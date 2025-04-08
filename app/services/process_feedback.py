from services.generate_feedback import generate_feedback
from utils.llm_router import query_openai, query_gemini, query_grok
from models import Comment, Session
from utils.redis_utils import Redis

def process_feedback(context: str, task_id: str):
    """
    背景任務：產生回饋並儲存至 Redis
    """
    try:
        feedback_text = query_openai(context)

        # 儲存至 Redis
        Redis.write_dict(f"feedback:{task_id}", {
            "status": "done",
            "result": feedback_text
        })

    except Exception as e:
        Redis.write_dict(f"feedback:{task_id}", {
            "status": "error",
            "message": str(e)
        })