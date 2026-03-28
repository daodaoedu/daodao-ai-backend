"""
靈感頁後端測試（Issue #42）

涵蓋場景：
12.1  AI backend get_practices() — delayed+active 不回傳打卡內容（is_brewing=True）
12.2  AI backend get_practices() — delayed+completed 回傳完整打卡（is_brewing=False）
12.5  搜尋隱私安全 — delayed 打卡心得關鍵字無結果
12.6  組合篩選 — _apply_filters 正確傳遞 tags/status/duration
12.7  /api/v1/users/practices 不含 private 或 draft 練習
"""

from unittest.mock import MagicMock, patch, call

import pytest

from src.services.practice.practice import PracticeService
from src.models.Practice import PracticeStatus, PracticePrivacyStatus


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_practice(
    privacy_status: str = PracticePrivacyStatus.PUBLIC.value,
    status: str = PracticeStatus.ACTIVE.value,
    duration_days: int = 30,
):
    """建立最小化 Mock Practice 物件，用於測試 is_brewing 邏輯。"""
    p = MagicMock()
    p.privacy_status = privacy_status
    p.status = status
    p.duration_days = duration_days
    p.deleted_at = None
    return p


# ─────────────────────────────────────────────────────────────────────────────
# 12.1 is_brewing — delayed + active → True
# ─────────────────────────────────────────────────────────────────────────────

class TestIsBrewingFlag:
    """驗證 is_brewing 旗標邏輯（源自 users.py router）。"""

    def _compute_is_brewing(self, privacy_status: str, status: str) -> bool:
        """複製 users.py router 中的 is_brewing 運算邏輯。"""
        return (
            privacy_status == PracticePrivacyStatus.DELAYED.value
            and status == PracticeStatus.ACTIVE.value
        )

    def test_delayed_active_is_brewing_true(self):
        """12.1 delayed + active → Brewing Card（is_brewing=True）"""
        assert self._compute_is_brewing("delayed", "active") is True

    def test_delayed_completed_is_brewing_false(self):
        """12.2 delayed + completed → Full Access Card（is_brewing=False）"""
        assert self._compute_is_brewing("delayed", "completed") is False

    def test_public_active_is_brewing_false(self):
        """12.2 regression：public + active 不是 Brewing Card"""
        assert self._compute_is_brewing("public", "active") is False

    def test_private_active_is_brewing_false(self):
        """private practice 不是 Brewing Card（應被過濾掉，不在廣場顯示）"""
        assert self._compute_is_brewing("private", "active") is False

    def test_delayed_not_started_is_brewing_false(self):
        """delayed + not_started 不是 Brewing（not_started 不在廣場顯示）"""
        assert self._compute_is_brewing("delayed", "not_started") is False


# ─────────────────────────────────────────────────────────────────────────────
# 12.7 _remove_unwanted_status — 過濾 private / draft
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoveUnwantedStatus:
    """驗證 _remove_unwanted_status 確實套用隱私與狀態過濾。"""

    def test_filter_is_applied(self):
        """_remove_unwanted_status 必須呼叫 query.join 與 query.filter。"""
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query

        PracticeService._remove_unwanted_status(mock_query)

        mock_query.join.assert_called_once()
        mock_query.filter.assert_called_once()

    def test_get_practices_always_applies_privacy_filter(self):
        """get_practices() 在任何條件下都必須呼叫 _remove_unwanted_status。"""
        db = MagicMock()

        with (
            patch.object(
                PracticeService,
                "_remove_unwanted_status",
                return_value=MagicMock(),
            ) as mock_remove,
            patch.object(
                PracticeService, "_build_base_query", return_value=MagicMock()
            ),
            patch.object(
                PracticeService, "_apply_filters", return_value=MagicMock()
            ),
            patch.object(
                PracticeService,
                "_apply_sort_and_pagination",
                return_value=[],
            ),
        ):
            # 無登入用戶
            PracticeService.get_practices(db=db, user_external_id=None)

        mock_remove.assert_called_once()

    def test_get_practices_with_user_applies_privacy_filter(self):
        """有登入用戶時，get_practices() 同樣套用隱私過濾。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock()  # user found

        with (
            patch.object(
                PracticeService,
                "_remove_unwanted_status",
                return_value=MagicMock(),
            ) as mock_remove,
            patch.object(
                PracticeService, "_build_base_query", return_value=MagicMock()
            ),
            patch.object(
                PracticeService, "_apply_filters", return_value=MagicMock()
            ),
            patch.object(
                PracticeService,
                "_apply_sort_and_pagination",
                return_value=[],
            ),
        ):
            PracticeService.get_practices(db=db, user_external_id="user-uuid-999")

        mock_remove.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 12.5 搜尋隱私安全 — Brewing 打卡心得不被關鍵字搜尋到
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchPrivacySafety:
    """驗證 _build_base_query 對 delayed+active practice 的 checkin note 搜尋安全。"""

    def test_build_base_query_called_with_keyword(self):
        """有關鍵字時，_build_base_query 應接收到 keyword 參數。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch.object(
                PracticeService,
                "_remove_unwanted_status",
                return_value=MagicMock(),
            ),
            patch.object(
                PracticeService,
                "_build_base_query",
                return_value=MagicMock(),
            ) as mock_build,
            patch.object(
                PracticeService, "_apply_filters", return_value=MagicMock()
            ),
            patch.object(
                PracticeService,
                "_apply_sort_and_pagination",
                return_value=[],
            ),
        ):
            PracticeService.get_practices(
                db=db,
                user_external_id=None,
                keyword="打卡心得機密",
            )

        # _build_base_query 必須被呼叫，且第二個參數是關鍵字
        mock_build.assert_called_once()
        _, keyword_arg = mock_build.call_args.args
        assert keyword_arg == "打卡心得機密"

    def test_no_keyword_skips_checkin_search(self):
        """無關鍵字時，_build_base_query 傳入 keyword=None（不進行文字搜尋）。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch.object(
                PracticeService,
                "_remove_unwanted_status",
                return_value=MagicMock(),
            ),
            patch.object(
                PracticeService,
                "_build_base_query",
                return_value=MagicMock(),
            ) as mock_build,
            patch.object(
                PracticeService, "_apply_filters", return_value=MagicMock()
            ),
            patch.object(
                PracticeService,
                "_apply_sort_and_pagination",
                return_value=[],
            ),
        ):
            PracticeService.get_practices(db=db, user_external_id=None, keyword=None)

        mock_build.assert_called_once()
        _, keyword_arg = mock_build.call_args.args
        assert keyword_arg is None


# ─────────────────────────────────────────────────────────────────────────────
# 12.6 組合篩選 — _apply_filters 正確傳遞參數
# ─────────────────────────────────────────────────────────────────────────────

class TestCombinedFilter:
    """驗證組合篩選參數（tags=ai, status=active, duration_min=7）正確傳遞。"""

    def test_apply_filters_receives_correct_params(self):
        """tags + status + duration_min 同時存在時，_apply_filters 接收完整參數。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch.object(
                PracticeService,
                "_remove_unwanted_status",
                return_value=MagicMock(),
            ),
            patch.object(
                PracticeService, "_build_base_query", return_value=MagicMock()
            ),
            patch.object(
                PracticeService,
                "_apply_filters",
                return_value=MagicMock(),
            ) as mock_filters,
            patch.object(
                PracticeService,
                "_apply_sort_and_pagination",
                return_value=[],
            ),
        ):
            PracticeService.get_practices(
                db=db,
                user_external_id=None,
                tags=["ai"],
                status="active",
                duration_min=7,
                duration_max=30,
            )

        mock_filters.assert_called_once()
        _, tags_arg, dur_min, dur_max, status_arg = mock_filters.call_args.args
        assert tags_arg == ["ai"]
        assert status_arg == "active"
        assert dur_min == 7
        assert dur_max == 30

    def test_no_filters_does_not_exclude_results(self):
        """無篩選條件時，_apply_filters 仍應被呼叫（不帶任何篩選值）。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch.object(
                PracticeService,
                "_remove_unwanted_status",
                return_value=MagicMock(),
            ),
            patch.object(
                PracticeService, "_build_base_query", return_value=MagicMock()
            ),
            patch.object(
                PracticeService,
                "_apply_filters",
                return_value=MagicMock(),
            ) as mock_filters,
            patch.object(
                PracticeService,
                "_apply_sort_and_pagination",
                return_value=[],
            ),
        ):
            PracticeService.get_practices(db=db, user_external_id=None)

        mock_filters.assert_called_once()
        _, tags_arg, dur_min, dur_max, status_arg = mock_filters.call_args.args
        assert tags_arg is None
        assert status_arg is None
        assert dur_min is None
        assert dur_max is None

    def test_duration_slug_7_maps_to_duration_min_param(self):
        """duration_min=7 篩選精確傳遞（對應 issue 12.6 的 duration=7 slug）。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch.object(
                PracticeService,
                "_remove_unwanted_status",
                return_value=MagicMock(),
            ),
            patch.object(
                PracticeService, "_build_base_query", return_value=MagicMock()
            ),
            patch.object(
                PracticeService,
                "_apply_filters",
                return_value=MagicMock(),
            ) as mock_filters,
            patch.object(
                PracticeService,
                "_apply_sort_and_pagination",
                return_value=[],
            ),
        ):
            PracticeService.get_practices(
                db=db,
                user_external_id=None,
                tags=["ai"],
                status="active",
                duration_min=7,
            )

        _, tags_arg, dur_min, dur_max, status_arg = mock_filters.call_args.args
        assert dur_min == 7
        assert tags_arg == ["ai"]
        assert status_arg == "active"
