"""
LLMModel 業務邏輯：
- seed_llm_models：lifespan 啟動時將 Settings.llm_backend 寫入 llm_models 表（冪等）
  只做 seed，不做健康檢查，不覆蓋 is_active。
- health_check_llm_models：啟動後背景執行，逐一呼叫各 provider API，
  成功 → is_active=True，失敗 → is_active=False。
"""

import asyncio
from decimal import Decimal
from typing import Optional, Any
from sqlalchemy.orm import Session

from src.config import Settings
from src.logger import AppLogger
from src.models.LLMModel import LLMModel

logger = AppLogger(__name__).get_logger()

# 已知模型費率（USD per 1M tokens）
# 來源：OpenAI / Google / Anthropic / Groq 官方定價頁
_KNOWN_COSTS: dict[tuple[str, str], dict[str, Decimal]] = {
    ("openai", "gpt-4o-mini"): {
        "input": Decimal("0.150000"),
        "output": Decimal("0.600000"),
        "cached_input": Decimal("0.075000"),
    },
    ("gemini", "gemini-2.0-flash"): {
        "input": Decimal("0.100000"),
        "output": Decimal("0.400000"),
        "cached_input": Decimal("0.025000"),
    },
    ("anthropic", "claude-3-haiku-20240307"): {
        "input": Decimal("0.250000"),
        "output": Decimal("1.250000"),
        "cached_input": Decimal("0.030000"),
    },
    ("groq", "llama-3.3-70b-versatile"): {
        "input": Decimal("0.590000"),
        "output": Decimal("0.790000"),
        "cached_input": Decimal("0.000000"),
    },
    ("ollama", "qwen2.5:1.5b"): {
        "input": Decimal("0.100000"),
        "output": Decimal("0.400000"),
        "cached_input": Decimal("0.000000"),
    },
}


async def seed_llm_models(
    db: Session, settings: Settings, cache: Optional[Any] = None
) -> None:
    """
    Lifespan 啟動時呼叫（冪等）：
    - 不存在 → insert（is_active=False，由 admin 手動啟用）
    - 存在 → 只補全費率（若全為 0），不動 is_active
    """
    for provider, config in settings.llm_backend.items():
        model_name = config.model
        costs = _KNOWN_COSTS.get((provider, model_name))

        existing = (
            db.query(LLMModel)
            .filter(
                LLMModel.provider == provider,
                LLMModel.model_name == model_name,
            )
            .first()
        )

        if existing is None:
            db.add(
                LLMModel(
                    provider=provider,
                    model_name=model_name,
                    display_name=f"{provider} / {model_name}",
                    is_active=False,
                    input_cost_per_1m=costs["input"] if costs else Decimal("0"),
                    output_cost_per_1m=costs["output"] if costs else Decimal("0"),
                    cached_input_cost_per_1m=(
                        costs["cached_input"] if costs else Decimal("0")
                    ),
                )
            )
            logger.info(f"[LLMModelSeed] 已插入 {provider}/{model_name}")
        else:
            # 只補全費率，不覆蓋 is_active
            if costs and (
                existing.input_cost_per_1m == 0
                and existing.output_cost_per_1m == 0
                and existing.cached_input_cost_per_1m == 0
            ):
                existing.input_cost_per_1m = costs["input"]
                existing.output_cost_per_1m = costs["output"]
                existing.cached_input_cost_per_1m = costs["cached_input"]
                logger.info(f"[LLMModelSeed] 費率已補全 {provider}/{model_name}")

    db.commit()

    # ── 清除模型列表快取 ──
    if cache:
        try:
            from src.routers.admin.llm_models import _MODELS_CACHE_KEY

            cache.client.delete(_MODELS_CACHE_KEY)
            logger.info(f"[LLMModelSeed] 已清除快取: {_MODELS_CACHE_KEY}")
        except Exception as e:
            logger.warning(f"[LLMModelSeed] 清除快取失敗: {e}")


async def health_check_llm_models(
    database: Any,
    settings: Settings,
    cache: Optional[Any] = None,
    timeout: float = 10.0,
) -> None:
    """
    啟動後背景執行（asyncio.create_task）：
    對每個 llm_models 記錄發送測試 prompt，依結果更新 is_active。
    不阻塞 API 啟動，失敗不影響服務。
    """
    from src.services.llm.client import LLMClient

    # 略過不需要外部 API key 的本地 provider
    _SKIP_PROVIDERS = {"ollama"}

    logger.info("[LLMHealthCheck] 開始背景 LLM 健康檢查...")

    async def _check_one(provider: str, model_name: str) -> bool:
        if provider in _SKIP_PROVIDERS:
            logger.info(f"[LLMHealthCheck] 跳過 {provider}（本地服務）")
            return False
        try:
            client = LLMClient(settings, provider, enable_guardrail=False)
            client._backend.config["model"] = model_name
            output, _, _, _ = await asyncio.wait_for(
                client.generate("reply ok", max_tokens=5),
                timeout=timeout,
            )
            ok = bool(output and output.strip())
            logger.info(f"[LLMHealthCheck] ✅ {provider}/{model_name}")
            return ok
        except asyncio.TimeoutError:
            logger.warning(f"[LLMHealthCheck] ⏱ timeout {provider}/{model_name}")
            return False
        except Exception as e:
            logger.warning(f"[LLMHealthCheck] ❌ {provider}/{model_name}: {e}")
            return False

    with database.get_session() as db:
        models = db.query(LLMModel).all()
        if not models:
            logger.warning("[LLMHealthCheck] llm_models 表為空，跳過")
            return

        tasks = {
            m.id: asyncio.create_task(_check_one(m.provider, m.model_name))
            for m in models
        }
        results = {mid: await task for mid, task in tasks.items()}

        for m in models:
            new_active = results.get(m.id, False)
            if m.is_active != new_active:
                m.is_active = new_active

        db.commit()

    active = sum(1 for v in results.values() if v)
    logger.info(f"[LLMHealthCheck] 完成：{active}/{len(results)} 個 provider 可用")

    if cache:
        try:
            from src.routers.admin.llm_models import _MODELS_CACHE_KEY

            cache.client.delete(_MODELS_CACHE_KEY)
        except Exception:
            pass
