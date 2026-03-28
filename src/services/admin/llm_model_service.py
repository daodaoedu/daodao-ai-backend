"""
LLMModel 業務邏輯：
- seed_llm_models：lifespan 啟動時將 Settings.llm_backend 寫入 llm_models 表（冪等）
  若紀錄已存在但費率仍為 0，則自動補上已知費率。
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from src.config import Settings
from src.logger import AppLogger
from src.models.LLMModel import LLMModel

logger = AppLogger(__name__).get_logger()

# 已知模型費率（USD per 1M tokens）
# 來源：OpenAI / Google / Anthropic / Groq 官方定價頁（2025-03）
_KNOWN_COSTS: dict[tuple[str, str], dict[str, Decimal]] = {
    ("openai", "gpt-4o"): {
        "input": Decimal("2.500000"),
        "output": Decimal("10.000000"),
        "cached_input": Decimal("1.250000"),
    },
    ("gemini", "gemini-2.0-flash"): {
        "input": Decimal("0.100000"),
        "output": Decimal("0.400000"),
        "cached_input": Decimal("0.025000"),
    },
    ("anthropic", "claude-3-5-sonnet-20241022"): {
        "input": Decimal("3.000000"),
        "output": Decimal("15.000000"),
        "cached_input": Decimal("0.300000"),
    },
    ("groq", "llama-3.3-70b-versatile"): {
        "input": Decimal("0.590000"),
        "output": Decimal("0.790000"),
        "cached_input": Decimal("0.000000"),  # Groq 不支援 prompt caching
    },
    # ollama / qwen2.5:1.5b：本地執行，暫無定價 → 先隨便設定，後續若有定價再更新
    ("ollama", "qwen2.5:1.5b"): {
        "input": Decimal("0.100000"),
        "output": Decimal("0.400000"),
        "cached_input": Decimal("0.000000"),
    },
    
}


def seed_llm_models(db: Session, settings: Settings) -> None:
    """
    Lifespan 啟動時呼叫：
    - 不存在 → insert（含費率）
    - 已存在但三個費率欄位皆為 0 → 補上已知費率（backfill）
    - 已存在且費率已設定 → 跳過
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
                    is_active=True,
                    input_cost_per_1m=costs["input"] if costs else Decimal("0"),
                    output_cost_per_1m=costs["output"] if costs else Decimal("0"),
                    cached_input_cost_per_1m=costs["cached_input"] if costs else Decimal("0"),
                )
            )
            logger.info(f"[LLMModelSeed] 已插入 {provider}/{model_name}")

        elif costs and (
            existing.input_cost_per_1m == 0
            and existing.output_cost_per_1m == 0
            and existing.cached_input_cost_per_1m == 0
        ):
            # 已存在但費率全為 0 → backfill
            existing.input_cost_per_1m = costs["input"]
            existing.output_cost_per_1m = costs["output"]
            existing.cached_input_cost_per_1m = costs["cached_input"]
            logger.info(f"[LLMModelSeed] 費率已補全 {provider}/{model_name}")

        else:
            logger.debug(f"[LLMModelSeed] {provider}/{model_name} 已存在，跳過")

    db.commit()
