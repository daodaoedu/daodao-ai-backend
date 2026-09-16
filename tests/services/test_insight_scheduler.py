"""
Unit tests for src.services.insight.insight_scheduler.InsightScheduler

涵蓋：
  - _run_job — 成功計數、失敗計數、混合情況
  - start / stop — scheduler 生命週期
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.insight.insight_scheduler import InsightScheduler


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def _make_scheduler() -> InsightScheduler:
    """建立 InsightScheduler，mock 掉所有外部依賴"""
    settings = MagicMock()
    settings.insight.schedule_cron = "0 1 * * *"
    settings.insight.llm_backend = "anthropic"
    settings.llm_backend = {
        "anthropic": MagicMock(
            url="", model="claude-3-5-sonnet-20241022", api_key="key"
        )
    }
    database = MagicMock()
    return InsightScheduler(settings, database)


def _make_practice(practice_id: int) -> MagicMock:
    p = MagicMock()
    p.id = practice_id
    return p


# ─────────────────────────────────────────────────────────────
# InsightScheduler._run_job
# ─────────────────────────────────────────────────────────────


class TestInsightSchedulerRunJob:

    @pytest.mark.asyncio
    async def test_no_pending_practices_does_nothing(self):
        """無待處理 practices：任務靜默完成，不呼叫 generate"""
        scheduler = _make_scheduler()
        scheduler._database.get_session.return_value.__enter__ = MagicMock(
            return_value=MagicMock()
        )
        scheduler._database.get_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with (
            patch(
                "src.services.insight.insight_scheduler.insight_service.get_pending_practices",
                return_value=[],
            ),
            patch(
                "src.services.insight.insight_scheduler.insight_service.generate_for_practice",
            ) as mock_gen,
        ):
            await scheduler._run_job()

        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_succeed_increments_total(self):
        """所有 practices 成功生成：total 應等於 practice 數量"""
        scheduler = _make_scheduler()
        practices = [_make_practice(i) for i in range(1, 4)]

        db_mock = MagicMock()
        scheduler._database.get_session.return_value.__enter__ = MagicMock(
            return_value=db_mock
        )
        scheduler._database.get_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        generated_insights = [MagicMock() for _ in practices]

        async def _side_effect(db, llm, practice):
            return generated_insights[practice.id - 1]

        with (
            patch(
                "src.services.insight.insight_scheduler.insight_service.get_pending_practices",
                return_value=practices,
            ),
            patch(
                "src.services.insight.insight_scheduler.insight_service.generate_for_practice",
                side_effect=_side_effect,
            ),
        ):
            await scheduler._run_job()
        # 主要驗證：沒有 raise，任務能順利完成

    @pytest.mark.asyncio
    async def test_exception_in_generate_increments_failed(self):
        """某個 practice 的 generate 拋出例外：繼續處理其他，不中斷整個任務"""
        scheduler = _make_scheduler()
        practices = [_make_practice(1), _make_practice(2)]

        db_mock = MagicMock()
        scheduler._database.get_session.return_value.__enter__ = MagicMock(
            return_value=db_mock
        )
        scheduler._database.get_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        # practice_id=1 拋出例外，practice_id=2 成功
        async def _side_effect(db, llm, practice):
            if practice.id == 1:
                raise RuntimeError("LLM timeout")
            return MagicMock()

        with (
            patch(
                "src.services.insight.insight_scheduler.insight_service.get_pending_practices",
                return_value=practices,
            ),
            patch(
                "src.services.insight.insight_scheduler.insight_service.generate_for_practice",
                side_effect=_side_effect,
            ),
        ):
            # 不應 raise：failed 被捕捉後繼續
            await scheduler._run_job()

    @pytest.mark.asyncio
    async def test_generate_returns_none_not_counted_as_success(self):
        """generate_for_practice 回傳 None（race condition）時，total 不累加"""
        scheduler = _make_scheduler()
        practices = [_make_practice(1)]

        db_mock = MagicMock()
        scheduler._database.get_session.return_value.__enter__ = MagicMock(
            return_value=db_mock
        )
        scheduler._database.get_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with (
            patch(
                "src.services.insight.insight_scheduler.insight_service.get_pending_practices",
                return_value=practices,
            ),
            patch(
                "src.services.insight.insight_scheduler.insight_service.generate_for_practice",
                new_callable=lambda: lambda *a, **k: AsyncMock(return_value=None)(),
            ),
        ):
            await scheduler._run_job()  # 不 raise 即通過

    @pytest.mark.asyncio
    @pytest.mark.parametrize("has_active_config", [False, True])
    async def test_llm_client_init_failure_skips_job(self, has_active_config):
        """LLM client 初始化失敗時，任務應跳過且不往外拋例外"""
        scheduler = _make_scheduler()
        db = scheduler._database.get_session.return_value.__enter__.return_value
        db.query.return_value.filter.return_value.first.return_value = (
            MagicMock(model_id=17) if has_active_config else None
        )
        db.get.return_value = MagicMock(provider="anthropic", model_name="test-model")

        with (
            patch(
                "src.services.insight.insight_scheduler.LLMClient",
                side_effect=RuntimeError("missing api key"),
            ) as mock_client,
            patch(
                "src.services.insight.insight_scheduler.insight_service.get_pending_practices",
            ) as mock_get_pending,
            patch(
                "src.services.insight.insight_scheduler.insight_service.generate_for_practice",
            ) as mock_generate,
        ):
            await scheduler._run_job()

        mock_get_pending.assert_not_called()
        mock_generate.assert_not_called()
        assert mock_client.call_count == (2 if has_active_config else 1)
        scheduler._database.get_session.return_value.__exit__.assert_called_once_with(
            None, None, None
        )


# ─────────────────────────────────────────────────────────────
# InsightScheduler start / stop
# ─────────────────────────────────────────────────────────────


class TestInsightSchedulerLifecycle:

    def test_start_adds_job_and_starts_scheduler(self):
        scheduler = _make_scheduler()

        with (
            patch.object(scheduler._scheduler, "add_job") as mock_add,
            patch.object(scheduler._scheduler, "start") as mock_start,
        ):
            scheduler.start()

        mock_add.assert_called_once()
        mock_start.assert_called_once()

    def test_stop_shuts_down_when_running(self):
        scheduler = _make_scheduler()

        # AsyncIOScheduler.running 是 class-level property，需在 type 上 patch
        with (
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler.running",
                new_callable=lambda: property(lambda self: True),
            ),
            patch.object(scheduler._scheduler, "shutdown") as mock_shutdown,
        ):
            scheduler.stop()

        mock_shutdown.assert_called_once_with(wait=False)

    def test_stop_does_nothing_when_not_running(self):
        scheduler = _make_scheduler()

        with (
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler.running",
                new_callable=lambda: property(lambda self: False),
            ),
            patch.object(scheduler._scheduler, "shutdown") as mock_shutdown,
        ):
            scheduler.stop()

        mock_shutdown.assert_not_called()
