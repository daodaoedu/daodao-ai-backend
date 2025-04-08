from typing import Dict, List, Optional
import json
from datetime import datetime

from utils.llm_router import choose_llm

class ReviewService:
    def __init__(self):
        self.review_prompt_template = """
        請根據以下資料進行分析並提供個人化的回饋與建議：

        使用者資料：
        {user_data}

        歷史記錄：
        {history_data}

        請提供以下方面的分析：
        1. 整體表現評估
        2. 進步的領域
        3. 需要改進的地方
        4. 具體的改進建議
        5. 下一步行動計畫

        請以結構化的方式呈現分析結果。
        """

    def _prepare_review_prompt(self, user_data: Dict, history_data: List[Dict]) -> str:
        """準備發送給 LLM 的 prompt"""
        formatted_user_data = json.dumps(user_data, ensure_ascii=False, indent=2)
        formatted_history = json.dumps(history_data, ensure_ascii=False, indent=2)

        return self.review_prompt_template.format(
            user_data=formatted_user_data,
            history_data=formatted_history
        )

    def generate_review(self,
                       user_data: Dict,
                       history_data: List[Dict],
                       review_type: Optional[str] = None) -> Dict:
        """生成個人化的回饋與建議"""

        prompt = self._prepare_review_prompt(user_data, history_data)

        # 使用 LLM 生成回饋
        llm_response = choose_llm(prompt)

        # 整理回應結果
        review_result = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_data.get("user_id"),
            "review_type": review_type or "general",
            "analysis": llm_response,
            "raw_data": {
                "user_data": user_data,
                "history_data": history_data
            }
        }

        return review_result

    def analyze_progress(self,
                        user_data: Dict,
                        history_data: List[Dict],
                        specific_aspects: Optional[List[str]] = None) -> Dict:
        """分析使用者的進步情況"""

        progress_prompt = f"""
        請分析以下使用者的進步情況：

        使用者資料：
        {json.dumps(user_data, ensure_ascii=False, indent=2)}

        歷史記錄：
        {json.dumps(history_data, ensure_ascii=False, indent=2)}

        需要特別關注的方面：
        {json.dumps(specific_aspects, ensure_ascii=False, indent=2) if specific_aspects else '所有方面'}

        請提供：
        1. 各個方面的進步程度評估
        2. 進步最顯著的領域
        3. 進步較慢的領域
        4. 建議的改進方向
        """

        analysis = choose_llm(progress_prompt)

        return {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_data.get("user_id"),
            "progress_analysis": analysis,
            "analyzed_aspects": specific_aspects or ["overall"],
            "raw_data": {
                "user_data": user_data,
                "history_data": history_data
            }
        }
