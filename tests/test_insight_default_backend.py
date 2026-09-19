"""InsightSettings 預設 backend 必須是 cloudflare（groq 免費層模型已下架，dev env 未設 INSIGHT__LLM_BACKEND 時不能壞）"""

from src.config import InsightSettings


def test_insight_default_backend_is_cloudflare(monkeypatch):
    monkeypatch.delenv("INSIGHT__LLM_BACKEND", raising=False)
    settings = InsightSettings(_env_file=None)
    assert settings.llm_backend == "cloudflare"
