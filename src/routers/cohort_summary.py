from fastapi import APIRouter, HTTPException, Request

from src.dependencies import SettingsDep, UserDep
from src.logger import AppLogger
from src.middleware.limiter import limiter
from src.schemas.cohort_summary import (
    CohortSummaryEntry,
    GenerateCohortSummaryRequest,
    GenerateCohortSummaryResponse,
)
from src.services.llm.client import LLMClient

logger = AppLogger(__name__).get_logger()

router = APIRouter(prefix="/v1/cohort-summary", tags=["cohort-summary"])

PROMPT_VERSION = "cohort-summary-v1"
PHASE_LABELS = {
    "not_started": "尚未開始",
    "in_progress": "進行中（資料仍在累積）",
    "ended": "已結束",
}
MOOD_LABELS = {
    "give_up": "想放棄",
    "frustrated": "有點挫折",
    "bored": "有點無聊",
    "neutral": "平常心",
    "good": "不錯",
    "happy": "很開心",
}
# 單次 prompt 的資料量上限（字元），超過就從最舊的開始截，避免塞爆 context
ENTRIES_CHAR_BUDGET = 24_000


def _format_entry(entry: CohortSummaryEntry) -> str:
    kind = "留言" if entry.kind == "comment" else "打卡"
    mood = f"，心情：{MOOD_LABELS.get(entry.mood, entry.mood)}" if entry.mood else ""
    practice = f"／{entry.practice}" if entry.practice else ""
    return (
        f"- [{entry.date}] {entry.participant}{practice}（{kind}{mood}）：{entry.text}"
    )


def _build_prompt(req: GenerateCohortSummaryRequest) -> str:
    lines = [_format_entry(entry) for entry in req.entries]
    # 保留最新的內容：從尾端往回塞到預算為止
    kept: list[str] = []
    used = 0
    for line in reversed(lines):
        if used + len(line) > ENTRIES_CHAR_BUDGET:
            break
        kept.append(line)
        used += len(line)
    kept.reverse()
    omitted = len(lines) - len(kept)
    omitted_note = f"（另有 {omitted} 筆較早的紀錄未列出）\n" if omitted else ""

    cohort = req.cohort
    period = (
        f"{cohort.startDate or '?'} ～ {cohort.endDate or '?'}"
        if cohort.startDate or cohort.endDate
        else "未提供"
    )
    program = f"（系列：{cohort.programName}）" if cohort.programName else ""

    return f"""你是一位溫暖、觀察細膩的學習陪跑教練，正在為一個學習場次撰寫「成果摘要」，讀者是這個場次的帶領人。

場次資訊：
- 名稱：{cohort.name}{program}
- 期間：{period}
- 狀態：{PHASE_LABELS.get(cohort.phase, cohort.phase)}
- 參與人數：{cohort.participants}；總打卡數：{cohort.checkins}

以下是參與者的打卡筆記與留言（已去識別化，稱呼為「參與者 N」）：
{omitted_note}{chr(10).join(kept)}

請根據上述內容撰寫摘要，要求：
- 使用繁體中文，語氣溫暖、具體、像在和帶領人分享觀察，不要空泛。
- 分成三段，每段 2 到 4 句：第一段整體參與情形與氛圍；第二段值得被看見的亮點與具體例子（引用時用「參與者 N」）；第三段觀察到的共同卡點與給帶領人的溫和建議。
- 不要排名、不要比較個人、不要用「表現最差」「落後」等評價性字眼；不要捏造資料中沒有的事。
- 若狀態是進行中，請在結尾提醒這是進行中的資料。
- 只輸出摘要本文，不要標題、前後綴、引號或條列符號。"""


def _resolve_client(
    settings, provider: str | None, api_key: str | None
) -> tuple[LLMClient, str]:
    """組織自帶 key → request-scoped client；否則用平台預設 backend"""
    if api_key:
        backend = (provider or "openai").lower()
        try:
            return LLMClient.with_credentials(settings, backend, api_key), "own"
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    backend = settings.insight.llm_backend
    try:
        return LLMClient(settings, backend), "platform"
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"平台 AI 尚未設定：{exc}") from exc


@router.post("/generate", response_model=GenerateCohortSummaryResponse)
@limiter.limit("5/minute")
async def generate_cohort_summary(
    request: Request,
    current_user: UserDep,
    req: GenerateCohortSummaryRequest,
    settings: SettingsDep,
):
    """依場次打卡與留言產生成果摘要（繁體中文，三段）。"""
    if current_user is None:
        raise HTTPException(status_code=401, detail="未通過身份驗證")

    client, mode = _resolve_client(settings, req.provider, req.apiKey)
    prompt = _build_prompt(req)
    try:
        output, _cost, usage, backend_name = await client.generate(
            prompt, max_tokens=1200, temperature=0.5
        )
    except Exception as exc:  # LLM provider 錯誤（key 無效、額度、逾時…）
        logger.error(f"cohort summary 產生失敗（{mode}）: {exc}")
        raise HTTPException(
            status_code=502, detail=f"AI 產生摘要失敗：{type(exc).__name__}"
        ) from exc

    summary = (output or "").strip()
    if not summary:
        raise HTTPException(status_code=502, detail="AI 沒有回傳摘要內容")

    return GenerateCohortSummaryResponse(
        summary=summary,
        provider=backend_name,
        model=client.model,
        usage=usage or {},
        promptVersion=PROMPT_VERSION,
    )
