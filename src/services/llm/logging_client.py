"""
LoggingLLMClient — 包裝 LLMClient，在每次 generate() 後同步寫入 AIQueryLog。

使用方式（duck-typing，介面與 LLMClient 相同）：
    client = LoggingLLMClient(
        llm_client=LLMClient(settings, backend),
        db_session_factory=database.get_session,
        context="insight",
        user_id=None,
    )
    output, cost, usage, backend_name = await client.generate(prompt)
"""

import asyncio
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.logger import AppLogger
from src.services.llm.client import LLMClient

logger = AppLogger(__name__).get_logger()

# Keep blocking DB workers separate from the loop's DNS/default executor.
# Threads start lazily, are reused, and are joined by concurrent.futures at exit.
_DB_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="llm-quota-db")


class LoggingLLMClient:
    """
    包裝 LLMClient，所有 generate() 呼叫完後同步寫入 AIQueryLog。
    DB session 不共用 request session；受限使用者的 lock、check、log commit
    由同一 DB worker/session 完成，因此 scheduler 也可使用。
    """

    def __init__(
        self,
        llm_client: LLMClient,
        db_session_factory: Callable[[], AbstractContextManager],
        context: str = "unknown",
        user_id: Optional[str] = None,
        service_config_id: Optional[int] = None,
    ):
        self._client = llm_client
        self._session_factory = db_session_factory
        self.context = context
        self.user_id = user_id
        self.service_config_id = service_config_id
        # 透傳 LLMClient 的 backend 名稱，供外部識別
        self.backend = llm_client.backend

    async def generate(
        self,
        prompt: str,
        **kwargs,
    ) -> Tuple[str, float, Dict[str, Any], str]:
        """
        呼叫 LLM 並記錄查詢日誌。
        回傳 (output, cost, usage, backend_name)，與 LLMClient.generate() 相同。

        若 user_id 不為 None，呼叫前先檢查 token quota。
        QuotaExceededError 向上拋出，由呼叫端決定如何處理。
        """
        loop = asyncio.get_running_loop()
        admitted = loop.create_future()
        outcome = Future()
        cancelled = threading.Event()
        worker = loop.run_in_executor(
            _DB_EXECUTOR, self._admit_and_log, loop, admitted, outcome, cancelled
        )
        try:
            await asyncio.shield(admitted)
        except BaseException:
            cancelled.set()
            outcome.set_result(None)
            try:
                await self._finish_worker(worker)
            finally:
                if admitted.done() and not admitted.cancelled():
                    admitted.exception()
            raise

        start_ms = time.monotonic()
        status = "success"
        error_message: Optional[str] = None
        output = ""
        cost = 0.0
        usage: Dict[str, Any] = {}
        backend_name = self._client.backend

        try:
            output, cost, usage, backend_name = await self._client.generate(
                prompt, **kwargs
            )
        except asyncio.CancelledError:
            status = "error"
            error_message = "Generation cancelled"
            raise
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - start_ms) * 1000)
            outcome.set_result(
                dict(
                    backend_name=backend_name,
                    cost=cost,
                    usage=usage,
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error_message,
                    prompt_chars=len(prompt),
                    output_chars=len(output),
                )
            )
            await self._finish_worker(worker)

        return output, cost, usage, backend_name

    @staticmethod
    async def _finish_worker(worker: asyncio.Future) -> None:
        """Cancellation must not return a connection before its owner cleans up."""
        cancellation = None
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError as exc:
                cancellation = exc
        worker.result()
        if cancellation is not None:
            raise cancellation

    def _admit_and_log(
        self,
        loop: asyncio.AbstractEventLoop,
        admitted: asyncio.Future,
        outcome: Future,
        cancelled: threading.Event,
    ) -> None:
        """Own the synchronous Session entirely in one worker, never on the loop.

        The lock covers fresh admission through committed usage. The provider
        runs on the caller's loop; its result is handed back to this worker.
        """
        from src.services.quota_service import (  # noqa: PLC0415
            check_user_quota,
            get_user_quota,
        )

        admission_sent = False

        def notify(error: Optional[Exception] = None) -> None:
            nonlocal admission_sent
            if error is None:
                admission_sent = True

            def complete() -> None:
                if not admitted.done():
                    if error is None:
                        admitted.set_result(None)
                    else:
                        admitted.set_exception(error)

            loop.call_soon_threadsafe(complete)

        try:
            if self.user_id is not None:
                with self._session_factory() as db:
                    user_id = int(self.user_id)
                    if get_user_quota(db, user_id) is not None:
                        if db.get_bind().dialect.name == "postgresql":
                            # A transaction-scoped lock also releases on rollback,
                            # disconnect, or process exit; no pooled lock leaks.
                            while not cancelled.is_set():
                                locked = db.scalar(
                                    text(
                                        "SELECT pg_try_advisory_xact_lock(:namespace, :user_id)"
                                    ),
                                    {"namespace": 160, "user_id": user_id},
                                )
                                if locked:
                                    break
                                cancelled.wait(0.05)
                            if cancelled.is_set():
                                return
                        # READ COMMITTED plus expire_all observes changes made
                        # while waiting instead of reusing an ORM cached quota.
                        db.expire_all()
                        check_user_quota(db, user_id)
                        if cancelled.is_set():
                            return
                        notify()
                        entry = outcome.result()
                        if entry is not None:
                            self._write_log(**entry, db=db)
                        return
            # No quota remains unrestricted and holds no pool connection while
            # the provider runs (including scheduler calls with user_id=None).
            if cancelled.is_set():
                return
            notify()
            entry = outcome.result()
            if entry is not None:
                self._write_log(**entry)
        except Exception as exc:
            if admission_sent:
                raise
            notify(exc)

    def _write_log(
        self,
        backend_name: str,
        cost: float,
        usage: Dict[str, Any],
        latency_ms: int,
        status: str,
        error_message: Optional[str],
        prompt_chars: int,
        output_chars: int = 0,
        db: Optional[Session] = None,
    ) -> None:
        """Commit usage on the admission session, or an independent unbounded-call session."""
        # 延遲 import 避免循環依賴
        from src.models.AIQueryLog import AIQueryLog  # noqa: PLC0415

        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0

        # 從 backend config 取得 model name
        model_name: Optional[str] = None
        try:
            model_name = self._client._backend.config.get("model")  # type: ignore[attr-defined]
        except Exception:
            pass

        log_entry = AIQueryLog(
            request_id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            backend=backend_name,
            model_name=model_name,
            context=self.context,
            user_id=self.user_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
            usage_detail=usage,
            prompt_chars=prompt_chars,
            output_chars=output_chars,
            finish_reason=usage.get("finish_reason"),
            service_config_id=self.service_config_id,
        )

        try:
            if db is not None:
                db.add(log_entry)
                db.commit()
            else:
                with self._session_factory() as session:
                    session.add(log_entry)
                    session.commit()
        except Exception as exc:
            if db is not None:
                db.rollback()
            # Log write 失敗不可影響呼叫者
            logger.error(f"[LoggingLLMClient] 寫入 AIQueryLog 失敗: {exc}")
