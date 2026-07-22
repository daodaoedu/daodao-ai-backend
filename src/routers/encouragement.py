from fastapi import APIRouter, HTTPException, Request

from src.dependencies import LLMDep, UserDep
from src.logger import AppLogger
from src.middleware.limiter import limiter
from src.schemas.encouragement import (
    GenerateEncouragementRequest,
    GenerateEncouragementResponse,
)

logger = AppLogger(__name__).get_logger()

router = APIRouter(prefix="/v1/encouragement", tags=["encouragement"])


def _build_prompt(req: GenerateEncouragementRequest) -> str:
    nickname = req.learnerNickname or "這位學員"

    mood_line = f"- 目前心情：{req.mood}" if req.mood else "- 目前心情：未填寫"
    if req.note:
        note_line = f"- 打卡心得：{req.note}"
    else:
        note_line = "- 打卡心得：未填寫（請把焦點放在練習本身）"

    return f"""你是一位溫暖、細膩的學習教練，正在為學員撰寫一段鼓勵訊息。

學員資訊：
- 暱稱：{nickname}
- 正在進行的練習：{req.practiceTitle}
{mood_line}
{note_line}

請根據上述打卡內容，寫一段 2 到 3 句的鼓勵訊息，要求：
- 使用繁體中文，語氣親切自然，像真人教練在對話。
- 具體呼應學員實際填寫的心得或練習內容，不要用空泛的場面話。
- 若心情偏負面（挫折、無聊、想放棄），要格外同理，先接住情緒再給予支持。
- 若心得為空，就把焦點放在這個練習本身，肯定學員願意持續練習。
- 只輸出鼓勵訊息本身，不要加任何前後綴、標題、引號或說明。"""


@router.post("/generate", response_model=GenerateEncouragementResponse)
@limiter.limit("10/minute")
async def generate_encouragement(
    request: Request,
    current_user: UserDep,
    req: GenerateEncouragementRequest,
    llm_client: LLMDep,
):
    """依打卡內容生成一段個人化鼓勵訊息（繁體中文）。"""
    if current_user is None:
        raise HTTPException(status_code=401, detail="未通過身份驗證")

    prompt = _build_prompt(req)
    output, _cost, _usage, _backend_name = await llm_client.generate(prompt)

    return GenerateEncouragementResponse(draft=output.strip())
