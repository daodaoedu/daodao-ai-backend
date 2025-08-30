import requests
from config import LLM_BACKENDS
from logger import AppLogger

logger = AppLogger(__name__).get_logger()


# ---
# LLM Token/Cost 計算說明：
#
# 1. OpenAI GPT-4（gpt-4）
#    - 官方回傳 usage（prompt_tokens, completion_tokens）
#    - 定價：prompt $0.03/1K tokens，completion $0.06/1K tokens
#    - 官方定價網址：https://openai.com/pricing
#    - cost = prompt_tokens/1000*0.03 + completion_tokens/1000*0.06
#    - 若無 usage，則用 (prompt+output) 字數/4 粗估 token，並以 $0.09/1K tokens 粗估
#
# 2. Gemini 2.0 Flash（Google）
#    - API 無 usage，僅能用 (prompt+output) 字數/4 粗估 token
#    - 定價：$0.35/1M input tokens，$1.05/1M output tokens
#    - 官方定價網址：https://cloud.google.com/vertex-ai/generative-ai/pricing
#    - cost = input_tokens/1_000_000*0.35 + output_tokens/1_000_000*1.05
#    - 本程式以 $0.0014/1K input，$0.0042/1K output 粗估（若無法區分 input/output，則合併 token 以 $0.0056/1K 粗估）
#    - estimated_tokens = max(1, len(prompt+output)//4)
#
# 3. Grok-2-latest（xAI）
#    - API 無 usage，僅能用 (prompt+output) 字數/4 粗估 token
#    - 定價：暫無公開，假設 $0.01/1K tokens
#    - 官方網站：https://x.ai/
#    - cost = estimated_tokens/1000*0.01
#    - estimated_tokens = max(1, len(prompt+output)//4)
# ---
def estimate_openai_cost(usage: dict) -> float:
    # OpenAI GPT-4o 新版 API usage fields: input_tokens, input_tokens_details, output_tokens, output_tokens_details, total_tokens
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    input_tokens_details = usage.get("input_tokens_details", {})
    cached_tokens = input_tokens_details.get("cached_tokens", 0)
    # OpenAI GPT-4o 價格: $5.00/1M input tokens, $2.50/1M cached input tokens, $20.00/1M output tokens
    # https://openai.com/pricing
    normal_input_tokens = (
        input_tokens - cached_tokens if input_tokens > cached_tokens else 0
    )
    input_cost = normal_input_tokens / 1_000_000 * 5.00
    cached_input_cost = cached_tokens / 1_000_000 * 2.50
    output_cost = output_tokens / 1_000_000 * 20.00
    total_cost = input_cost + cached_input_cost + output_cost
    if input_tokens or output_tokens or cached_tokens:
        return round(total_cost, 6)
    # fallback: 只用 total_tokens 粗估 (OpenAI fallback 以 $0.025/1K 粗估)
    total_tokens = usage.get("total_tokens", 0)
    return round(total_tokens / 1000 * 0.025, 6)


def estimate_token_cost(token_count: int, rate_per_1k: float = 0.01) -> float:
    return round(token_count / 1000 * rate_per_1k, 6)


def estimate_tokens(text: str) -> int:
    # 粗估 1 token ~ 4 字元
    return max(1, len(text) // 4)


def query_openai(prompt: str) -> tuple[str, float, dict, str]:
    url = LLM_BACKENDS["openai"]["url"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_BACKENDS['openai']['api_key']}",
    }
    payload = {"model": LLM_BACKENDS["openai"]["model"], "input": prompt}
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        output = (
            data.get("output", [{}])[0].get("content", [{}])[0].get("text", "未提供回應")
        )
        usage = data.get("usage", {})
        cost = (
            estimate_openai_cost(usage)
            if usage
            else estimate_token_cost(estimate_tokens(prompt + output), 0.09)
        )
        return output, cost, usage, "query_openai"
    else:
        return f"錯誤：API 請求失敗，狀態碼 {response.status_code}", 0, {}, "query_openai"


def query_gemini(prompt: str) -> tuple[str, float, dict, str]:
    url = f"{LLM_BACKENDS['gemini']['url']}/?key={LLM_BACKENDS['gemini']['api_key']}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        output = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "未提供回應")
        )
        # Gemini 沒有 usage，估算 token
        tokens = estimate_tokens(prompt + output)
        cost = estimate_token_cost(tokens, 0.01)
        usage = {"estimated_tokens": tokens}
        return output, cost, usage, "query_gemini"
    else:
        return f"錯誤：API 請求失敗，狀態碼 {response.status_code}", 0, {}, "query_gemini"


def query_ollama(prompt: str) -> tuple[str, float, dict, str]:
    """
    調用本地 Ollama /api/generate
    """
    url = LLM_BACKENDS["ollama"]["url"]
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": LLM_BACKENDS["ollama"]["model"],
        "prompt": prompt,
        "max_tokens": 500,
        "temperature": 0.7,
    }
    logger.info(f"url: {url}")
    logger.info(f"payload: {payload}")

    try:
        response = requests.post(
            url, headers=headers, json=payload, timeout=60
        )  # 設定 timeout 為 60
        response.raise_for_status()
        data = response.json()
        output = data.get("completion", "未提供回應")
        tokens = estimate_tokens(prompt + output)
        cost = estimate_token_cost(tokens, 0.005)  # 假設本地成本極低
        usage = {"estimated_tokens": tokens}
        return output, cost, usage, "query_ollama"
    except Exception as e:
        return f"錯誤：{str(e)}", 0, {}, "query_ollama"


def query_grok(prompt: str) -> tuple[str, float, dict, str]:
    url = LLM_BACKENDS["grok"]["url"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_BACKENDS['grok']['api_key']}",
    }
    payload = {
        "messages": [
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": prompt},
        ],
        "model": LLM_BACKENDS["grok"]["model"],
        "stream": False,
        "temperature": 0,
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        output = data.get("choices", [{}])[0].get("message", {}).get("content", "未提供回應")
        tokens = estimate_tokens(prompt + output)
        cost = estimate_token_cost(tokens, 0.01)
        usage = {"estimated_tokens": tokens}
        return output, cost, usage, "query_grok"
    else:
        return f"錯誤：API 請求失敗，狀態碼 {response.status_code}", 0, {}, "query_grok"


def choose_llm(prompt: str) -> tuple[str, float, dict]:
    """選擇適合的 LLM 服務，並回傳 (output, cost, usage)"""
    if "AI" in prompt:
        return query_gemini(prompt)
    elif "code" in prompt:
        return query_openai(prompt)
    else:
        return query_grok(prompt)


def test_choose_llm():
    # 測試案例 1: 包含 'AI' 的提示應選擇 Gemini
    prompt_ai = "Explain how AI works"
    response_ai = choose_llm(prompt_ai)
    logger.info(f"Response for AI prompt: {response_ai}")
    assert "AI" in response_ai, f"Expected Gemini, but got {response_ai}"

    # 測試案例 2: 包含 'code' 的提示應選擇 OpenAI
    # prompt_code = "Write a Python code that adds two numbers"
    # response_code = choose_llm(prompt_code)
    # logger.info(f"Response for code prompt: {response_code}")
    # assert "Python" in response_code, f"Expected OpenAI, but got {response_code}"

    # # # 測試案例 3: 其他情況應選擇 Grok
    # prompt_other = "Tell me a joke"
    # response_other = choose_llm(prompt_other)
    # logger.info(f"Response for other prompt: {response_other}")
    # assert "joke" in response_other, f"Expected Grok, but got {response_other}"


# test_choose_llm()
