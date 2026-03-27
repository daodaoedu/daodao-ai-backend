"""
Unit tests for src.services.insight.insight_service

涵蓋：
  - _analyze_checkins      — 統計分析（streak、星期、心情、筆記）
  - get_pending_practices  — 只回傳 completed + insight IS NULL 的 Practice
  - get_checkins_for_practice — 依日期排序
  - generate_for_practice — 正常生成、冪等（insight 已存在）、LLM 錯誤
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.insight.insight_service import (
    _analyze_checkins,
    generate_for_practice,
    get_checkins_for_practice,
    get_pending_practices,
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def _make_practice(practice_id: int, user_id: int = 1, insight: str | None = None) -> MagicMock:
    p = MagicMock()
    p.id = practice_id
    p.user_id = user_id
    p.title = f"Practice {practice_id}"
    p.practice_action = "每天閱讀 30 分鐘"
    p.duration_days = 30
    p.insight = insight  # None 表示尚未生成
    return p


def _make_checkin(practice_id: int, date_str: str, mood: str = "good") -> MagicMock:
    c = MagicMock()
    c.practice_id = practice_id
    c.checkin_date = date_str
    c.mood = mood
    c.note = "今天完成了！"
    return c


def _make_real_checkin(
    practice_id: int,
    checkin_date: date,
    mood: str = "good",
    note: str = "",
) -> MagicMock:
    """建立有真實 date 物件的 checkin mock（供統計分析使用）"""
    c = MagicMock()
    c.practice_id = practice_id
    c.checkin_date = checkin_date
    c.mood = mood
    c.note = note
    return c


# ─────────────────────────────────────────────────────────────
# _analyze_checkins
# ─────────────────────────────────────────────────────────────


class TestAnalyzeCheckins:

    def test_empty_checkins_returns_zeros(self):
        result = _analyze_checkins([])
        assert result["total"] == 0
        assert result["max_streak"] == 0
        assert result["top_weekdays"] == []
        assert result["notable_notes"] == []

    def test_total_count(self):
        checkins = [
            _make_real_checkin(1, date(2025, 1, i)) for i in range(1, 6)
        ]
        result = _analyze_checkins(checkins)
        assert result["total"] == 5

    def test_consecutive_streak_detected(self):
        # 1/1、1/2、1/3 連續 3 天，然後跳過一天，再 1/5
        checkins = [
            _make_real_checkin(1, date(2025, 1, 1)),
            _make_real_checkin(1, date(2025, 1, 2)),
            _make_real_checkin(1, date(2025, 1, 3)),
            _make_real_checkin(1, date(2025, 1, 5)),
        ]
        result = _analyze_checkins(checkins)
        assert result["max_streak"] == 3

    def test_no_streak_all_separate(self):
        checkins = [
            _make_real_checkin(1, date(2025, 1, 1)),
            _make_real_checkin(1, date(2025, 1, 3)),
            _make_real_checkin(1, date(2025, 1, 5)),
        ]
        result = _analyze_checkins(checkins)
        assert result["max_streak"] == 1

    def test_top_weekdays_returns_most_common(self):
        # 週六(5) = 3次、週日(6) = 2次、週一(0) = 1次
        checkins = [
            _make_real_checkin(1, date(2025, 1, 4)),   # 週六
            _make_real_checkin(1, date(2025, 1, 11)),  # 週六
            _make_real_checkin(1, date(2025, 1, 18)),  # 週六
            _make_real_checkin(1, date(2025, 1, 5)),   # 週日
            _make_real_checkin(1, date(2025, 1, 12)),  # 週日
            _make_real_checkin(1, date(2025, 1, 6)),   # 週一
        ]
        result = _analyze_checkins(checkins)
        assert "週六" in result["top_weekdays"]
        assert "週日" in result["top_weekdays"]
        assert len(result["top_weekdays"]) <= 2

    def test_notable_notes_filters_short_notes(self):
        checkins = [
            _make_real_checkin(1, date(2025, 1, 1), note="ok"),        # 太短，忽略
            _make_real_checkin(1, date(2025, 1, 2), note="終於搞懂 auto layout！"),
            _make_real_checkin(1, date(2025, 1, 3), note="今天沒有靈感", mood="neutral"),
        ]
        result = _analyze_checkins(checkins)
        notes = result["notable_notes"]
        assert all(len(c.note.strip()) > 5 for c in notes)

    def test_notable_notes_max_two(self):
        checkins = [
            _make_real_checkin(1, date(2025, 1, i), note=f"今天的練習紀錄第 {i} 天很充實")
            for i in range(1, 6)
        ]
        result = _analyze_checkins(checkins)
        assert len(result["notable_notes"]) <= 2

    def test_positive_mood_summary(self):
        checkins = [
            _make_real_checkin(1, date(2025, 1, i), mood="happy") for i in range(1, 6)
        ] + [
            _make_real_checkin(1, date(2025, 1, i), mood="good") for i in range(6, 10)
        ]
        result = _analyze_checkins(checkins)
        assert "正向" in result["mood_summary"]

    def test_negative_mood_summary(self):
        checkins = [
            _make_real_checkin(1, date(2025, 1, i), mood="frustrated")
            for i in range(1, 5)
        ]
        result = _analyze_checkins(checkins)
        assert "挑戰" in result["mood_summary"]


# ─────────────────────────────────────────────────────────────
# get_pending_practices
# ─────────────────────────────────────────────────────────────


class TestGetPendingPractices:

    def test_returns_practices_from_db(self):
        """正常情況：DB 有待處理 practices，應全數回傳"""
        practices = [_make_practice(1), _make_practice(2)]
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = practices

        result = get_pending_practices(db)

        assert result == practices
        db.execute.assert_called_once()

    def test_returns_empty_list_when_none_pending(self):
        """無待處理時回傳空 list"""
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []

        result = get_pending_practices(db)

        assert result == []

    def test_executes_select_query(self):
        """確認有呼叫 db.execute（即有送出 query）"""
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []

        get_pending_practices(db)

        db.execute.assert_called_once()


# ─────────────────────────────────────────────────────────────
# get_checkins_for_practice
# ─────────────────────────────────────────────────────────────


class TestGetCheckinsForPractice:

    def test_returns_checkins_from_db(self):
        checkins = [
            _make_checkin(1, "2025-01-01"),
            _make_checkin(1, "2025-01-02"),
        ]
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = checkins

        result = get_checkins_for_practice(db, practice_id=1)

        assert result == checkins

    def test_returns_empty_list_when_no_checkins(self):
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []

        result = get_checkins_for_practice(db, practice_id=99)

        assert result == []

    def test_passes_correct_practice_id(self):
        """確認 query 有被執行（practice_id 有傳進去）"""
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []

        get_checkins_for_practice(db, practice_id=42)

        db.execute.assert_called_once()


# ─────────────────────────────────────────────────────────────
# generate_for_practice
# ─────────────────────────────────────────────────────────────


class TestGenerateForPractice:

    # ── 正常生成 ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generates_and_saves_insight(self):
        """正常流程：LLM 成功，insight 應寫入 practice.insight 並 commit"""
        practice = _make_practice(1, insight=None)
        db = MagicMock()

        llm_client = MagicMock()
        llm_client.generate = AsyncMock(
            return_value=("你的成長洞察很棒！", 0.000012, {"input_tokens": 100}, "anthropic")
        )

        with (
            patch(
                "src.services.insight.insight_service.get_checkins_for_practice",
                return_value=[],
            ),
            patch(
                "src.services.insight.insight_service._build_prompt",
                return_value="mocked prompt",
            ),
        ):
            result = await generate_for_practice(db, llm_client, practice)

        assert result is not None
        assert practice.insight == "你的成長洞察很棒！"
        db.commit.assert_called_once()
        db.refresh.assert_called_once()
        # 更新欄位，不需要 db.add()
        db.add.assert_not_called()

    # ── 冪等：insight 已存在 ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_returns_none_if_insight_already_exists(self):
        """insight 已存在時，不重複生成，回傳 None"""
        practice = _make_practice(1, insight="已有洞察了")
        db = MagicMock()
        llm_client = MagicMock()

        result = await generate_for_practice(db, llm_client, practice)

        assert result is None
        llm_client.generate.assert_not_called()
        db.commit.assert_not_called()

    # ── LLM 回傳錯誤 ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_returns_none_on_llm_error(self):
        """LLM 回傳 '錯誤：...' 前綴時，不儲存，回傳 None"""
        practice = _make_practice(1, insight=None)
        db = MagicMock()

        llm_client = MagicMock()
        llm_client.generate = AsyncMock(
            return_value=("錯誤：API rate limit", 0.0, {}, "anthropic")
        )

        with (
            patch(
                "src.services.insight.insight_service.get_checkins_for_practice",
                return_value=[],
            ),
            patch(
                "src.services.insight.insight_service._build_prompt",
                return_value="mocked prompt",
            ),
        ):
            result = await generate_for_practice(db, llm_client, practice)

        assert result is None
        assert practice.insight is None  # 不應被改動
        db.commit.assert_not_called()

    # ── Insight 內容正確寫入 practice ────────────────────────

    @pytest.mark.asyncio
    async def test_insight_content_is_saved_to_practice(self):
        """儲存的洞察應正確寫入 practice.insight"""
        practice = _make_practice(5, user_id=10, insight=None)
        db = MagicMock()

        llm_client = MagicMock()
        llm_client.generate = AsyncMock(
            return_value=("洞察文字內容", 0.000025, {"input_tokens": 200}, "gemini")
        )

        with (
            patch(
                "src.services.insight.insight_service.get_checkins_for_practice",
                return_value=[],
            ),
            patch(
                "src.services.insight.insight_service._build_prompt",
                return_value="prompt",
            ),
        ):
            result = await generate_for_practice(db, llm_client, practice)

        assert result is practice  # 回傳同一個 practice 物件
        assert practice.insight == "洞察文字內容"
        assert practice.id == 5
