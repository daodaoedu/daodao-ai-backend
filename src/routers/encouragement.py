from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import String, select

from src.dependencies import DatabaseDep, LLMDep, UserDep
from src.logger import AppLogger
from src.middleware.limiter import limiter
from src.models.User import User
from src.services.llm.logging_client import LoggingLLMClient
from src.services.quota_service import QuotaExceededError
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
    database: DatabaseDep,
):
    """依打卡內容生成一段個人化鼓勵訊息（繁體中文）。"""
    if current_user is None:
        raise HTTPException(status_code=401, detail="未通過身份驗證")

    # JWT identities may be PostgreSQL ids or legacy Mongo/external ids.
    # Quotas and query logs always use the canonical PostgreSQL users.id.
    with database.get_session() as db:
        user_id = None
        if (
            current_user.isascii()
            and current_user.isdecimal()
            and len(current_user) <= 10
            and int(current_user) <= 2**31 - 1
        ):
            # users.id is a PostgreSQL INTEGER; longer numeric Mongo ids fall back.
            user_id = db.scalar(select(User.id).where(User.id == int(current_user)))
        if user_id is None:
            user_id = db.scalar(select(User.id).where(User.mongo_id == current_user))
        if user_id is None:
            user_id = db.scalar(
                select(User.id).where(User.external_id.cast(String) == current_user)
            )
    if user_id is None:
        raise HTTPException(status_code=401, detail="未通過身份驗證")

    logging_client = LoggingLLMClient(
        llm_client=llm_client,
        db_session_factory=database.get_session,
        context="encouragement",
        user_id=str(user_id),
    )
    prompt = _build_prompt(req)
    try:
        output, _cost, _usage, _backend_name = await logging_client.generate(prompt)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=429, detail="Token 配額已用盡") from exc

    return GenerateEncouragementResponse(draft=output.strip())
