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
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy import func, text
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import Session

from src.logger import AppLogger
from src.services.llm.client import LLMClient

logger = AppLogger(__name__).get_logger()

# Short DB operations never occupy a worker while a provider runs. Cleanup has
# reserved capacity and only touches an already-held connection, so saturated
# pool checkouts cannot prevent a completed generation releasing its connection.
_DB_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="llm-quota-db")
_CLEANUP_EXECUTOR = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="llm-quota-cleanup"
)
_LOG_EXECUTOR = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="llm-unrestricted-log"
)


@dataclass
class _Admission:
    manager: Optional[AbstractContextManager] = None
    db: Optional[Session] = None


class LoggingLLMClient:
    """
    包裝 LLMClient，所有 generate() 呼叫完後同步寫入 AIQueryLog。
    DB session 不共用 request session；受限使用者的 lock、check、log commit
    使用同一 Session 的循序操作完成（不並行共用），因此 scheduler 也可使用。
    """

    def __init__(
        self,
        llm_client: LLMClient,
        db_session_factory: Callable[[], AbstractContextManager],
        context: str = "unknown",
        user_id: Optional[str] = None,
        service_config_id: Optional[int] = None,
        quota_session_factory: Optional[Callable[[], AbstractContextManager]] = None,
    ):
        self._client = llm_client
        self._session_factory = db_session_factory
        self._quota_session_factory = quota_session_factory or db_session_factory
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
        guard = _Admission()
        while self.user_id is not None:
            guard, cancellation = await self._settle(
                loop.run_in_executor(_DB_EXECUTOR, self._try_admit)
            )
            if cancellation is not None:
                if guard is not None and guard.db is not None:
                    await self._settle(
                        loop.run_in_executor(
                            _CLEANUP_EXECUTOR, self._finish_admission, guard, None
                        )
                    )
                raise cancellation
            if guard is not None:
                break
            # A lock waiter owns neither a worker nor a DB connection.
            await asyncio.sleep(0.05)

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
            error_message = type(exc).__name__
            raise
        finally:
            entry = None
            try:
                latency_ms = int((time.monotonic() - start_ms) * 1000)
                entry = dict(
                    backend_name=backend_name,
                    cost=cost,
                    usage=usage,
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error_message,
                    prompt_chars=len(prompt),
                    output_chars=len(output),
                )
            finally:
                # Even malformed provider data that fails before log creation
                # must close the held transaction/lock without coercing output.
                executor = _CLEANUP_EXECUTOR if guard.db is not None else _LOG_EXECUTOR
                _, cancellation = await self._settle(
                    loop.run_in_executor(executor, self._finish_admission, guard, entry)
                )
                if cancellation is not None:
                    raise cancellation

        return output, cost, usage, backend_name

    @staticmethod
    async def _settle(
        operation: asyncio.Future,
    ) -> Tuple[Any, Optional[asyncio.CancelledError]]:
        """Finish a short DB operation despite cancellation; always retrieve errors."""
        cancellation = None
        while True:
            try:
                result = await asyncio.shield(operation)
                return result, cancellation
            except asyncio.CancelledError as exc:
                cancellation = exc
            except Exception:
                if cancellation is not None:
                    raise cancellation
                raise

    def _try_admit(self) -> Optional[_Admission]:
        """One nonblocking admission attempt; Session operations are sequential.

        psycopg2 connections support sequential use across threads. A held guard
        is touched only by its finish operation after provider completion; no
        Session is used concurrently or through a scoped/thread-local factory.
        """
        from src.services.quota_service import (  # noqa: PLC0415
            check_user_quota,
            get_user_quota,
        )

        if self.user_id is None:
            return _Admission()
        user_id = int(self.user_id)
        # Metadata lookup and unrestricted logs use the ordinary pool. A full
        # quota guard pool must not turn an unconfigured user into a waiter.
        with self._session_factory() as metadata:
            if get_user_quota(metadata, user_id) is None:
                return _Admission()

        manager = self._quota_session_factory()
        manager_open = False
        try:
            db = manager.__enter__()
            manager_open = True
            if db.get_bind().dialect.name == "postgresql":
                locked = db.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:namespace, :user_id)"),
                    {"namespace": 160, "user_id": user_id},
                )
                if not locked:
                    manager_open = False
                    manager.__exit__(None, None, None)
                    return None
            db.expire_all()
            check_user_quota(db, user_id)
            return _Admission(manager, db)
        except SQLAlchemyTimeoutError as exc:
            # Only the isolated guard attempt is retryable. Ordinary metadata
            # lookup errors above still propagate; exhaustion is not a denial.
            if manager_open:
                manager.__exit__(type(exc), exc, exc.__traceback__)
            return None
        except BaseException as exc:
            if manager_open:
                manager.__exit__(type(exc), exc, exc.__traceback__)
            raise

    def _finish_admission(
        self, guard: _Admission, entry: Optional[Dict[str, Any]]
    ) -> None:
        """Reserved cleanup never checks out another connection for held guards."""
        try:
            if entry is not None:
                self._write_log(**entry, db=guard.db)
        except BaseException as exc:
            if guard.manager is not None:
                guard.manager.__exit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            if guard.manager is not None:
                guard.manager.__exit__(None, None, None)

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
            manager = nullcontext(db) if db is not None else self._session_factory()
            with manager as session:
                # PostgreSQL transaction NOW() predates lock/provider waits.
                # Attribute usage to completion using the database clock, not
                # an application host whose clock may be skewed.
                log_entry.created_at = (
                    func.clock_timestamp()
                    if session.get_bind().dialect.name == "postgresql"
                    else func.current_timestamp()
                )
                session.add(log_entry)
                session.commit()
        except Exception as exc:
            if db is not None:
                db.rollback()
            # Log write 失敗不可影響呼叫者
            logger.error(f"[LoggingLLMClient] 寫入 AIQueryLog 失敗: {exc}")
