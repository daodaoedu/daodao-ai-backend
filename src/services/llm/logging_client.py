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

import time
import uuid
from contextlib import AbstractContextManager
from typing import Any, Callable, Dict, Optional, Tuple

from src.logger import AppLogger
from src.services.llm.client import LLMClient

logger = AppLogger(__name__).get_logger()


class LoggingLLMClient:
    """
    包裝 LLMClient，所有 generate() 呼叫完後同步寫入 AIQueryLog。
    DB write 使用獨立 session（不共用 request session），因此 scheduler 也可使用。
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
        if self.user_id is not None:
            from src.services.quota_service import check_user_quota  # noqa: PLC0415

            with self._session_factory() as db:
                check_user_quota(db, int(self.user_id))

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
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - start_ms) * 1000)
            self._write_log(
                backend_name=backend_name,
                cost=cost,
                usage=usage,
                latency_ms=latency_ms,
                status=status,
                error_message=error_message,
                prompt_chars=len(prompt),
                output_chars=len(output),
            )

        return output, cost, usage, backend_name

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
    ) -> None:
        """同步寫入 AIQueryLog，使用獨立 session。失敗時只 log 不拋錯。"""
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
            with self._session_factory() as db:
                db.add(log_entry)
                db.commit()
        except Exception as exc:
            # Log write 失敗不可影響呼叫者
            logger.error(f"[LoggingLLMClient] 寫入 AIQueryLog 失敗: {exc}")
