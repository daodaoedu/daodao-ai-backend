import time

from fastapi import APIRouter, HTTPException

from src.dependencies import AdminDep, DatabaseDep, SessionDep, SettingsDep
from src.models.LLMModel import LLMModel
from src.models.SystemPrompt import SystemPrompt
from src.response_template import api_response_decorator
from src.schemas.admin.playground import PlaygroundChatRequest
from src.services.llm.client import LLMClient
from src.services.llm.logging_client import LoggingLLMClient
from src.services.quota_service import QuotaExceededError

router = APIRouter()


@router.post("/playground/chat")
@api_response_decorator
async def playground_chat(
    body: PlaygroundChatRequest,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    database: DatabaseDep,
    settings: SettingsDep,
) -> dict:
    """
    Playground：使用指定 LLM 模型與 system prompt 進行單次對話。
    每次呼叫都記錄到 ai_query_logs（context='playground'）。
    """
    # 1. 查詢 LLM 模型
    model = (
        db.query(LLMModel)
        .filter(LLMModel.id == body.model_id, LLMModel.is_active.is_(True))
        .first()
    )
    if model is None:
        raise HTTPException(status_code=404, detail=f"LLM model {body.model_id} not found or inactive")

    # 2. 組合 prompt
    system_content = ""
    if body.system_prompt_id is not None:
        sp = db.query(SystemPrompt).filter(SystemPrompt.id == body.system_prompt_id).first()
        if sp:
            system_content = sp.content

    full_prompt = f"{system_content}\n\n---\n{body.message}" if system_content else body.message

    # 3. 建立 LLM client（使用 model.provider 對應的 backend）
    llm_client = LLMClient(settings, model.provider)
    logging_client = LoggingLLMClient(
        llm_client=llm_client,
        db_session_factory=database.get_session,
        context="playground",
        user_id=str(admin.id),
    )

    # 4. 呼叫 LLM（quota 超限時拋 QuotaExceededError）
    start_ms = time.monotonic()
    try:
        output, cost, usage, backend_name = await logging_client.generate(full_prompt)
    except QuotaExceededError as e:
        kind_zh = "月" if e.kind == "monthly" else "日"
        raise HTTPException(
            status_code=429,
            detail=f"Token 配額已用盡（{kind_zh}限制）：已使用 {e.used:,} / 上限 {e.limit:,} tokens",
        )
    latency_ms = int((time.monotonic() - start_ms) * 1000)

    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0

    return {
        "data": {
            "response": output,
            "model_used": f"{model.provider}/{model.model_name}",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "latency_ms": latency_ms,
        },
        "pagination": None,
        "cache_hit": False,
    }
