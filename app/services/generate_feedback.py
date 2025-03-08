

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
    return "Test"

    url = "http://localhost:11434/api/chat"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "deepseek-r1:14b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1000,
        "stream": False
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": f"Request failed with status code {response.status_code}"}




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
