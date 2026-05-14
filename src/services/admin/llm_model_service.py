"""
LLMModel 業務邏輯：
- seed_llm_models：lifespan 啟動時將 Settings.llm_backend 寫入 llm_models 表（冪等）
  只做 seed，不做健康檢查，不覆蓋 is_active。
"""

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
