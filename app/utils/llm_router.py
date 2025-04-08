import requests
import json
from config import LLM_BACKENDS

def query_openai(prompt: str) -> str:
    url = LLM_BACKENDS['openai']['url']
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_BACKENDS['openai']['api_key']}"
    }
    payload = {
        "model": LLM_BACKENDS['openai']['model'],
        "input":  prompt
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json().get("output", [{}])[0].get("content", [{}])[0].get("text", "未提供回應")
    else:
        return f"錯誤：API 請求失敗，狀態碼 {response.status_code}"

def query_gemini(prompt: str) -> str:
    url = f"{LLM_BACKENDS['gemini']['url']}/?key={LLM_BACKENDS['gemini']['api_key']}"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "未提供回應")
    else:
        return f"錯誤：API 請求失敗，狀態碼 {response.status_code}"

def query_grok(prompt: str) -> str:
    url = LLM_BACKENDS['grok']['url']
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_BACKENDS['grok']['api_key']}"
    }
    payload = {
        "messages": [
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": prompt}
        ],
        "model":  LLM_BACKENDS['grok']['model'],
        "stream": False,
        "temperature": 0
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "未提供回應")
    else:
        return f"錯誤：API 請求失敗，狀態碼 {response.status_code}"

def choose_llm(prompt: str) -> str:
    """選擇適合的 LLM 服務"""
    if "AI" in prompt:
        return query_gemini(prompt)  # 解釋 AI 工作的話，選擇 Gemini
    elif "code" in prompt:
        return query_openai(prompt)  # 程式碼相關，選擇 OpenAI
    else:
        return query_grok(prompt)  # 其他情況，選擇 Grok
def test_choose_llm():
    # 測試案例 1: 包含 'AI' 的提示應選擇 Gemini
    # prompt_ai = "Explain how AI works"
    # response_ai = choose_llm(prompt_ai)
    # print(f"Response for AI prompt: {response_ai}")
    # assert "AI" in response_ai, f"Expected Gemini, but got {response_ai}"

    # 測試案例 2: 包含 'code' 的提示應選擇 OpenAI
    prompt_code = "Write a Python code that adds two numbers"
    response_code = choose_llm(prompt_code)
    print(f"Response for code prompt: {response_code}")
    assert "Python" in response_code, f"Expected OpenAI, but got {response_code}"

    # # # 測試案例 3: 其他情況應選擇 Grok
    # prompt_other = "Tell me a joke"
    # response_other = choose_llm(prompt_other)
    # print(f"Response for other prompt: {response_other}")
    # assert "joke" in response_other, f"Expected Grok, but got {response_other}"

test_choose_llm()
