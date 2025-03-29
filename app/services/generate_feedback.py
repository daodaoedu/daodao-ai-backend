import requests
import json


def generate_feedback(prompt: str) -> str:
    # response = openai.ChatCompletion.create(
    #     model="gpt-3.5-turbo",
    #     messages=[
    #         {"role": "system", "content": "你是一位精通學習策略的助理，請根據使用者的學習記錄提供具體而有建設性的回饋建議。"},
    #         {"role": "user", "content": f"以下是使用者的學習資料：{context}\n請根據這些資料，給予一則回饋建議。"}
    #     ],
    #     max_tokens=150,
    #     temperature=0.7
    # )
    # return response.choices[0].message.content.strip()
    # return "Test"
    prompt = "請用中文回覆，最多100字以內\n" + prompt
    url = "http://ollama:11434/api/chat"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "phi3:latest",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 200,
        "stream": False
    }

    response = requests.post(url, headers=headers, data=json.dumps(payload))

    if response.status_code == 200:
        response_json = response.json()
        return response_json.get('message', {}).get('content', '未提供回應內容')
    else:
        return f"錯誤：API 請求失敗，狀態碼 {response.status_code}"




# def generate_feedback(context: str) -> str:
#     """
#     呼叫 ChatGPT API 根據 context 產生回饋建議
#     """
#     try:
#         response = openai.ChatCompletion.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {
#                     "role": "system",
#                     "content": "你是一位精通學習策略的助理，請根據使用者的學習記錄提供具體而有建設性的回饋建議。"
#                 },
#                 {
#                     "role": "user",
#                     "content": f"以下是使用者的學習資料：{context}\n請根據這些資料，給予一則回饋建議。"
#                 }
#             ],
#             max_tokens=150,
#             temperature=0.7
#         )
#         return response.choices[0].message.content.strip()
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"ChatGPT API 呼叫失敗: {str(e)}")
