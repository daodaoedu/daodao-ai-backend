"""
Provider Model Sync Service
呼叫各 provider API 取得最新模型清單，upsert 進 llm_models 表。
新同步的模型 is_active=False，需 admin 手動啟用。
"""

from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import Settings
from src.logger import AppLogger

logger = AppLogger(__name__).get_logger()

SUPPORTED_PROVIDERS = {
    "groq",
    "openai",
    "anthropic",
    "gemini",
    "nvidia",
    "cerebras",
    "cloudflare",
    "ollama_cloud",
    "openrouter",
    "ollama",
}


async def sync_provider_models(
    provider: str,
    db: Session,
    settings: Settings,
) -> dict:
    """
    同步指定 provider 的模型清單到 llm_models 表。
    回傳 {"provider": ..., "added": int, "existing": int}
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"不支援的 provider: {provider}")

    models = await _fetch_models(provider, settings)

    added = 0
    existing = 0
    for m in models:
        display_name = (m.get("display_name") or "")[:200] or None
        result = db.execute(
            text("""
                INSERT INTO llm_models (provider, model_name, display_name, is_active,
                    input_cost_per_1m, output_cost_per_1m, cached_input_cost_per_1m)
                VALUES (:provider, :model_name, :display_name, false, 0, 0, 0)
                ON CONFLICT (provider, model_name)
                DO UPDATE SET display_name = EXCLUDED.display_name
                RETURNING (xmax = 0) AS inserted
            """),
            {
                "provider": provider,
                "model_name": m["model_name"],
                "display_name": display_name,
            },
        )
        row = result.fetchone()
        if row and row.inserted:
            added += 1
        else:
            existing += 1

    db.commit()
    logger.info(f"[ModelSync] provider={provider} added={added} existing={existing}")
    return {"provider": provider, "added": added, "existing": existing}


async def _fetch_models(provider: str, settings: Settings) -> list[dict]:
    """各 provider 的模型抓取實作，統一回傳 list[{"model_name": ..., "display_name": ...}]"""
    cfg = settings.llm_backend.get(provider)
    api_key = cfg.api_key if cfg else None

    if provider == "groq":
        return await _fetch_openai_models(
            "https://api.groq.com/openai/v1/models", api_key, provider
        )

    if provider == "openai":
        return await _fetch_openai_models(
            "https://api.openai.com/v1/models", api_key, provider
        )

    if provider == "nvidia":
        return await _fetch_openai_models(
            "https://integrate.api.nvidia.com/v1/models", api_key, provider
        )

    if provider == "cerebras":
        return await _fetch_openai_models(
            "https://api.cerebras.ai/v1/models", api_key, provider
        )

    if provider == "openrouter":
        return await _fetch_openrouter_models(api_key)

    if provider == "anthropic":
        return await _fetch_anthropic_models(api_key)

    if provider == "gemini":
        return await _fetch_gemini_models(api_key)

    if provider == "cloudflare":
        account_id = settings.cloudflare_account_id
        return await _fetch_cloudflare_models(account_id, api_key)

    if provider == "ollama_cloud":
        return await _fetch_ollama_cloud_models(api_key)

    if provider == "ollama":
        url = cfg.url if cfg else "http://ollama:11434"
        base = url.rstrip("/").replace("/api/generate", "").replace("/v1", "")
        return await _fetch_ollama_local_models(base)

    return []


async def _fetch_openai_models(
    url: str, api_key: Optional[str], provider: str
) -> list[dict]:
    """OpenAI-compatible /models endpoint"""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [
            {"model_name": m["id"], "display_name": m.get("id")}
            for m in data
            if isinstance(m, dict) and "id" in m
        ]


async def _fetch_openrouter_models(api_key: Optional[str]) -> list[dict]:
    """OpenRouter /models endpoint（只取 text 類型）"""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [
            {"model_name": m["id"], "display_name": m.get("name") or m.get("id")}
            for m in data
            if isinstance(m, dict)
            and "id" in m
            and m.get("architecture", {}).get("modality")
            in ("text->text", "text+image->text", None)
        ]


async def _fetch_anthropic_models(api_key: Optional[str]) -> list[dict]:
    """Anthropic /models endpoint"""
    headers = {
        "x-api-key": api_key or "",
        "anthropic-version": "2023-06-01",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://api.anthropic.com/v1/models", headers=headers)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [
            {
                "model_name": m["id"],
                "display_name": m.get("display_name") or m.get("id"),
            }
            for m in data
            if isinstance(m, dict) and "id" in m
        ]


async def _fetch_gemini_models(api_key: Optional[str]) -> list[dict]:
    """Google Gemini /models endpoint"""
    params = {"key": api_key} if api_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json().get("models", [])
        result = []
        for m in data:
            if not isinstance(m, dict):
                continue
            name = m.get("name", "")  # "models/gemini-2.0-flash"
            model_id = name.split("/")[-1] if "/" in name else name
            if not model_id:
                continue
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            result.append(
                {
                    "model_name": model_id,
                    "display_name": m.get("displayName") or model_id,
                }
            )
        return result


async def _fetch_cloudflare_models(
    account_id: str, api_key: Optional[str]
) -> list[dict]:
    """Cloudflare Workers AI models search endpoint"""
    if not account_id:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID 未設定")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json().get("result", [])
        result = []
        for m in data:
            if not isinstance(m, dict):
                continue
            task_type = m.get("task", {}).get("name", "")
            if "Text Generation" not in task_type:
                continue
            model_name = m.get("name", "")
            result.append(
                {
                    "model_name": model_name,
                    "display_name": m.get("description") or model_name,
                }
            )
        return result


async def _fetch_ollama_cloud_models(api_key: Optional[str]) -> list[dict]:
    """Ollama cloud models listing（https://ollama.com/api/tags）"""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://ollama.com/api/tags", headers=headers)
        resp.raise_for_status()
        data = resp.json().get("models", [])
        return [
            {"model_name": m["model"], "display_name": m.get("name") or m.get("model")}
            for m in data
            if isinstance(m, dict) and m.get("model")
        ]


async def _fetch_ollama_local_models(base_url: str) -> list[dict]:
    """Local Ollama /api/tags"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{base_url}/api/tags")
        resp.raise_for_status()
        data = resp.json().get("models", [])
        return [
            {"model_name": m["model"], "display_name": m.get("name") or m.get("model")}
            for m in data
            if isinstance(m, dict) and m.get("model")
        ]
