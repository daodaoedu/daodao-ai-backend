from collections import Counter
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.logger import AppLogger
from src.models.Practice import Practice, PracticeStatus
from src.models.PracticeCheckIn import PracticeCheckIn
from src.services.llm.client import LLMClient

logger = AppLogger(__name__).get_logger()

_PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "insight_system.txt"

# 星期中文對照
_WEEKDAY_ZH = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


def _load_system_prompt() -> str:
    if _PROMPT_FILE.exists():
        return _PROMPT_FILE.read_text(encoding="utf-8").strip()
    return "你是個人成長教練，請根據用戶的實踐記錄生成成長洞察。"


def _analyze_checkins(checkins: list) -> dict:
    """
    從打卡記錄提煉統計數據，供 prompt 使用。
    回傳：
      total         — 總打卡次數
      max_streak    — 最長連續天數
      top_weekdays  — 最常打卡的星期（最多 2 個）
      mood_summary  — 心情分布描述
      notable_notes — 有實質內容的筆記（最多 2 條）
    """
    if not checkins:
        return {
            "total": 0,
            "max_streak": 0,
            "top_weekdays": [],
            "mood_summary": "",
            "notable_notes": [],
        }

    total = len(checkins)

    # ── 最長連續打卡 ──────────────────────────────────────────
    sorted_dates = sorted(
        [c.checkin_date for c in checkins if c.checkin_date], key=lambda d: d
    )
    max_streak = 1
    current_streak = 1
    for i in range(1, len(sorted_dates)):
        delta = (sorted_dates[i] - sorted_dates[i - 1]).days
        if delta == 1:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        elif delta > 1:
            current_streak = 1

    # ── 最常打卡星期 ──────────────────────────────────────────
    weekday_counts: Counter = Counter(
        d.weekday() for d in sorted_dates  # 0=週一, 6=週日
    )
    top_weekdays = [_WEEKDAY_ZH[wd] for wd, _ in weekday_counts.most_common(2)]

    # ── 心情分布 ──────────────────────────────────────────────
    mood_counts: Counter = Counter(
        c.mood for c in checkins if c.mood and c.mood not in ("", "neutral")
    )
    positive = mood_counts.get("happy", 0) + mood_counts.get("good", 0)
    negative = mood_counts.get("frustrated", 0) + mood_counts.get("bored", 0)
    if positive > negative * 2:
        mood_summary = f"整體心情偏正向（happy/good 共 {positive} 次）"
    elif negative >= positive:
        mood_summary = f"過程有挑戰（frustrated/bored 共 {negative} 次，但你撐下來了）"
    else:
        mood_summary = f"心情起伏，但持續到最後（共打卡 {total} 次）"

    # ── 精選筆記（有實質文字的） ──────────────────────────────
    notes_with_content = [
        c for c in checkins if c.note and len(c.note.strip()) > 5
    ]
    # 優先選 mood=happy/frustrated 的（情緒最強的那幾天）
    priority = [
        c for c in notes_with_content if c.mood in ("happy", "frustrated")
    ]
    notable_notes = (priority + notes_with_content)[:2]

    return {
        "total": total,
        "max_streak": max_streak,
        "top_weekdays": top_weekdays,
        "mood_summary": mood_summary,
        "notable_notes": notable_notes,
    }


def _build_prompt(practice: Practice, checkins: list) -> str:
    """組合洞察生成 prompt"""
    system = _load_system_prompt()
    stats = _analyze_checkins(checkins)

    # ── 統計摘要 ──────────────────────────────────────────────
    weekday_str = "、".join(stats["top_weekdays"]) if stats["top_weekdays"] else "未知"
    stats_block = (
        f"總打卡次數：{stats['total']} 次\n"
        f"最長連續打卡：{stats['max_streak']} 天\n"
        f"最常練習日：{weekday_str}\n"
        f"心情概況：{stats['mood_summary']}"
    )

    # ── 精選筆記 ──────────────────────────────────────────────
    if stats["notable_notes"]:
        note_lines = []
        for c in stats["notable_notes"]:
            date_str = str(c.checkin_date) if c.checkin_date else "未知日期"
            mood_str = c.mood or "未記錄"
            note_lines.append(f'  - {date_str} | {mood_str} | 「{c.note.strip()}」')
        notes_block = "精選打卡筆記（情緒最鮮明的紀錄）：\n" + "\n".join(note_lines)
    else:
        notes_block = "精選打卡筆記：（用戶未留下筆記，請根據統計數據生成洞察）"

    user_data = (
        f"實踐標題：{practice.title}\n"
        f"目標行動：{practice.practice_action or '（未填寫）'}\n"
        f"持續天數：{practice.duration_days or '未設定'} 天\n\n"
        f"【實踐統計】\n{stats_block}\n\n"
        f"【{notes_block}】"
    )

    return f"{system}\n\n---\n以下是用戶的實踐資料：\n\n{user_data}"


def get_pending_practices(db: Session) -> List[Practice]:
    """
    查詢所有 status='completed' 且 insight IS NULL 的 Practice。
    insight 欄位為 NULL 表示尚未生成，確保冪等。
    """
    stmt = (
        select(Practice)
        .where(
            Practice.status == PracticeStatus.COMPLETED.value,
            Practice.deleted_at.is_(None),
            Practice.insight.is_(None),
        )
        .order_by(Practice.id)
    )
    return list(db.execute(stmt).scalars().all())


def get_checkins_for_practice(db: Session, practice_id: int) -> list:
    """取得某 practice 的所有打卡記錄，按日期排序"""
    stmt = (
        select(PracticeCheckIn)
        .where(PracticeCheckIn.practice_id == practice_id)
        .order_by(PracticeCheckIn.checkin_date)
    )
    return list(db.execute(stmt).scalars().all())


async def generate_for_practice(
    db: Session,
    llm_client: LLMClient,
    practice: Practice,
) -> Optional[Practice]:
    """
    為單一 Practice 生成洞察並寫入 practices.insight 欄位。
    若已存在（冪等）則直接回傳 None。
    """
    # 冪等：已有 insight 就跳過
    if practice.insight is not None:
        return None

    checkins = get_checkins_for_practice(db, practice.id)
    prompt = _build_prompt(practice, checkins)

    logger.info(
        f"[InsightService] 生成洞察 practice_id={practice.id} checkins={len(checkins)}"
    )

    output, _cost, _usage, backend_name = await llm_client.generate(
        prompt, max_tokens=600
    )

    if output.startswith("錯誤："):
        logger.error(f"[InsightService] LLM 失敗 practice_id={practice.id}: {output}")
        return None

    practice.insight = output
    db.commit()
    db.refresh(practice)
    logger.info(
        f"[InsightService] 洞察已寫入 practice_id={practice.id} backend={backend_name}"
    )
    return practice
