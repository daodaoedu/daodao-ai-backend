import re
import time

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, update

from src.dependencies import AdminDep, DatabaseDep, SessionDep, SettingsDep
from src.models.LLMModel import LLMModel
from src.models.Practice import Practice, PracticeStatus
from src.models.SystemPrompt import SystemPrompt
from src.models.User import User
from src.response_template import api_response_decorator
from src.schemas.admin.playground import (
    PlaygroundChatRequest,
    PlaygroundInsightRequest,
    SaveInsightRequest,
)
from src.services.insight.insight_service import (
    _analyze_checkins,
    _build_prompt,
    get_checkins_for_practice,
)
from src.services.llm.client import LLMClient
from src.services.llm.guardrail import GuardrailLayer, GuardrailViolationError
from src.services.llm.logging_client import LoggingLLMClient
from src.services.quota_service import QuotaExceededError

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def _split_thinking(output: str) -> tuple[str, str]:
    """Return (thinking_content, clean_content) stripped of <think> blocks."""
    thinking_parts = _THINK_RE.findall(output)
    thinking = "\n\n".join(p.strip() for p in thinking_parts)
    clean = _THINK_RE.sub("", output).strip()
    return thinking, clean


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
    model = db.query(LLMModel).filter(LLMModel.id == body.model_id).first()
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"LLM model {body.model_id} not found"
        )

    # 2. 組合 prompt
    try:
        safe_message = GuardrailLayer.sanitize_user_input(body.message)
    except GuardrailViolationError as exc:
        raise HTTPException(
            status_code=400, detail=f"訊息內容違反安全規則：{exc}"
        ) from exc

    system_content = ""
    if body.system_prompt_id is not None:
        sp = (
            db.query(SystemPrompt)
            .filter(SystemPrompt.id == body.system_prompt_id)
            .first()
        )
        if sp:
            system_content = sp.content

    full_prompt = (
        f"{system_content}\n\n---\n{safe_message}" if system_content else safe_message
    )

    # 3. 建立 LLM client（使用 model.provider 對應的 backend，覆寫 model_name）
    llm_client = LLMClient(settings, model.provider)
    llm_client._backend.config["model"] = model.model_name
    logging_client = LoggingLLMClient(
        llm_client=llm_client,
        db_session_factory=database.get_session,
        context="playground",
        user_id=str(admin.id),
    )

    # 4. 呼叫 LLM（quota 超限時拋 QuotaExceededError）
    start_ms = time.monotonic()
    try:
        generate_kwargs: dict = {}
        if body.max_tokens is not None:
            generate_kwargs["max_tokens"] = body.max_tokens
        if body.temperature is not None:
            generate_kwargs["temperature"] = body.temperature
        if body.top_p is not None:
            generate_kwargs["top_p"] = body.top_p
        if body.top_k is not None:
            generate_kwargs["top_k"] = body.top_k
        output, cost, usage, backend_name = await logging_client.generate(
            full_prompt, **generate_kwargs
        )
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


@router.get("/playground/insight/users")
@api_response_decorator
def list_insight_users(
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """回傳有 completed practice 的使用者清單（id + nickname）"""
    stmt = (
        select(User.id, User.nickname)
        .join(Practice, Practice.user_id == User.id)
        .where(
            Practice.status == PracticeStatus.COMPLETED.value,
            Practice.deleted_at.is_(None),
        )
        .distinct()
        .order_by(User.nickname)
    )
    rows = db.execute(stmt).all()
    return {
        "data": [{"id": r.id, "nickname": r.nickname} for r in rows],
        "pagination": None,
        "cache_hit": False,
    }


@router.get("/playground/insight/practices")
@api_response_decorator
def list_insight_practices(
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    user_id: int = Query(...),
) -> dict:
    """回傳指定使用者的 completed practices（id, title, has_insight）"""
    stmt = (
        select(Practice.id, Practice.title, Practice.insight)
        .where(
            Practice.user_id == user_id,
            Practice.status == PracticeStatus.COMPLETED.value,
            Practice.deleted_at.is_(None),
        )
        .order_by(Practice.updated_at.desc())
    )
    rows = db.execute(stmt).all()
    return {
        "data": [
            {"id": r.id, "title": r.title, "has_insight": r.insight is not None}
            for r in rows
        ],
        "pagination": None,
        "cache_hit": False,
    }


@router.post("/playground/insight")
@api_response_decorator
async def playground_insight(
    body: PlaygroundInsightRequest,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    database: DatabaseDep,
    settings: SettingsDep,
) -> dict:
    """Playground：使用指定模型與設定生成 insight，可選擇是否儲存。"""
    # 1. 查模型
    model = db.query(LLMModel).filter(LLMModel.id == body.model_id).first()
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"LLM model {body.model_id} not found"
        )

    # 2. 查 practice
    practice = (
        db.query(Practice)
        .filter(
            Practice.id == body.practice_id,
            Practice.deleted_at.is_(None),
        )
        .first()
    )
    if practice is None:
        raise HTTPException(
            status_code=404, detail=f"Practice {body.practice_id} not found"
        )

    # 3. 查 user
    user = db.query(User).filter(User.id == practice.user_id).first()

    # 4. 取打卡記錄
    checkins = get_checkins_for_practice(db, practice.id)

    # 5. 計算統計
    stats = _analyze_checkins(checkins)

    # 6. 解析 system prompt override（system_prompt_id 優先於 system_prompt_override）
    system_prompt_override = body.system_prompt_override
    if body.system_prompt_id is not None:
        sp = (
            db.query(SystemPrompt)
            .filter(SystemPrompt.id == body.system_prompt_id)
            .first()
        )
        if sp is None:
            raise HTTPException(
                status_code=404,
                detail=f"SystemPrompt {body.system_prompt_id} not found",
            )
        system_prompt_override = sp.content

    # 7. 組 prompt
    prompt = _build_prompt(
        practice=practice,
        checkins=checkins,
        db=db,
        user=user,
        include_user_profile=body.include_user_profile,
        include_practice_info=body.include_practice_info,
        include_checkin_stats=body.include_checkin_stats,
        include_notable_notes=body.include_notable_notes,
        system_prompt_override=system_prompt_override,
    )

    # 8. 建立 LLM client（覆寫 model 為 DB 紀錄的 model_name）
    llm_client = LLMClient(settings, model.provider)
    llm_client._backend.config["model"] = model.model_name
    logging_client = LoggingLLMClient(
        llm_client=llm_client,
        db_session_factory=database.get_session,
        context="playground_insight",
        user_id=str(admin.id),
    )

    # 8. 呼叫 LLM
    start_ms = time.monotonic()
    try:
        insight_kwargs: dict = {"max_tokens": body.max_tokens or 2000}
        if body.temperature is not None:
            insight_kwargs["temperature"] = body.temperature
        if body.top_p is not None:
            insight_kwargs["top_p"] = body.top_p
        if body.top_k is not None:
            insight_kwargs["top_k"] = body.top_k
        output, cost, usage, _backend_name = await logging_client.generate(
            prompt, **insight_kwargs
        )
    except QuotaExceededError as e:
        kind_zh = "月" if e.kind == "monthly" else "日"
        raise HTTPException(
            status_code=429,
            detail=f"Token 配額已用盡（{kind_zh}限制）：已使用 {e.used:,} / 上限 {e.limit:,} tokens",
        )
    latency_ms = int((time.monotonic() - start_ms) * 1000)

    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0

    thinking, clean_output = _split_thinking(output)

    # 9. 可選儲存（只存不含 <think> 的內容）
    saved = False
    if body.save:
        db.execute(
            update(Practice)
            .where(Practice.id == practice.id)
            .values(insight=clean_output)
        )
        db.commit()
        saved = True

    # 10. 組 user_profile_used
    user_profile_used = {}
    if user:
        for field in (
            "nickname",
            "personal_slogan",
            "professional_field",
            "custom_position",
            "education_stage",
        ):
            val = getattr(user, field, None)
            if val is not None:
                user_profile_used[field] = val
        if user.tag_list:
            user_profile_used["tag_list"] = user.tag_list
        if user.birth_date:
            from datetime import date as _date

            age = (_date.today() - user.birth_date).days // 365
            bracket = (age // 5) * 5
            user_profile_used["age_range"] = f"{bracket}-{bracket + 4} 歲"
        if user.basic_info and user.basic_info.self_introduction:
            user_profile_used["self_introduction"] = (
                user.basic_info.self_introduction.strip()
            )

    return {
        "data": {
            "insight": clean_output,
            "thinking": thinking or None,
            "prompt_used": prompt,
            "checkin_stats": {
                "total": stats["total"],
                "max_streak": stats["max_streak"],
                "top_weekdays": stats["top_weekdays"],
                "mood_summary": stats["mood_summary"],
            },
            "user_profile_used": user_profile_used,
            "model_used": f"{model.provider}/{model.model_name}",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "latency_ms": latency_ms,
            "saved": saved,
        },
        "pagination": None,
        "cache_hit": False,
    }


@router.post("/playground/insight/save")
@api_response_decorator
async def save_insight_result(
    body: SaveInsightRequest,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """Playground：直接儲存已預覽的 insight 文字，不重跑 LLM。"""
    practice = (
        db.query(Practice)
        .filter(
            Practice.id == body.practice_id,
            Practice.deleted_at.is_(None),
        )
        .first()
    )
    if practice is None:
        raise HTTPException(
            status_code=404, detail=f"Practice {body.practice_id} not found"
        )

    db.execute(
        update(Practice).where(Practice.id == practice.id).values(insight=body.insight)
    )
    db.commit()

    return {
        "data": {"saved": True, "practice_id": body.practice_id},
        "pagination": None,
        "cache_hit": False,
    }
