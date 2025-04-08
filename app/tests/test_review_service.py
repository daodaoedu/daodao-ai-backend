import pytest
import json
import sys
import os
from datetime import datetime

# 添加項目根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.services.review_service import ReviewService

@pytest.fixture
def review_service():
    return ReviewService()

@pytest.fixture
def sample_user_data():
    return {
        "user_id": "test_user_123",
        "name": "測試用戶",
        "level": "intermediate",
        "focus_areas": ["python", "machine_learning", "web_development"],
        "join_date": "2024-01-01"
    }

@pytest.fixture
def sample_history_data():
    return [
        {
            "date": "2024-01-15",
            "activity_type": "project_completion",
            "project_name": "API開發專案",
            "metrics": {
                "code_quality": 8.5,
                "completion_time": "2週",
                "team_collaboration": 9.0
            },
            "feedback": "良好的代碼結構和文檔"
        },
        {
            "date": "2024-02-15",
            "activity_type": "skill_assessment",
            "skills": {
                "python": 8.0,
                "api_design": 7.5,
                "testing": 6.5
            },
            "improvements": ["測試覆蓋率提升", "API文檔完整性"]
        },
        {
            "date": "2024-03-15",
            "activity_type": "project_completion",
            "project_name": "機器學習模型部署",
            "metrics": {
                "model_accuracy": 0.85,
                "deployment_success": True,
                "code_quality": 8.8
            },
            "feedback": "成功實現模型優化和部署"
        }
    ]

def test_generate_review(review_service, sample_user_data, sample_history_data):
    """測試生成回饋功能"""
    # 測試一般回饋生成
    result = review_service.generate_review(
        user_data=sample_user_data,
        history_data=sample_history_data
    )

    # 驗證回應結構
    assert isinstance(result, dict)
    assert "timestamp" in result
    assert "user_id" in result
    assert "review_type" in result
    assert "analysis" in result
    assert "raw_data" in result

    # 驗證內容
    assert result["user_id"] == sample_user_data["user_id"]
    assert result["review_type"] == "general"
    assert isinstance(result["analysis"], str)
    assert len(result["analysis"]) > 0

    # 測試特定類型的回饋
    monthly_review = review_service.generate_review(
        user_data=sample_user_data,
        history_data=sample_history_data,
        review_type="monthly"
    )
    assert monthly_review["review_type"] == "monthly"

def test_analyze_progress(review_service, sample_user_data, sample_history_data):
    """測試進度分析功能"""
    # 測試整體進度分析
    result = review_service.analyze_progress(
        user_data=sample_user_data,
        history_data=sample_history_data
    )

    # 驗證回應結構
    assert isinstance(result, dict)
    assert "timestamp" in result
    assert "user_id" in result
    assert "progress_analysis" in result
    assert "analyzed_aspects" in result
    assert "raw_data" in result

    # 驗證內容
    assert result["user_id"] == sample_user_data["user_id"]
    assert isinstance(result["progress_analysis"], str)
    assert len(result["progress_analysis"]) > 0
    assert result["analyzed_aspects"] == ["overall"]

    # 測試特定方面的進度分析
    specific_aspects = ["python", "api_design"]
    specific_result = review_service.analyze_progress(
        user_data=sample_user_data,
        history_data=sample_history_data,
        specific_aspects=specific_aspects
    )
    assert specific_result["analyzed_aspects"] == specific_aspects

def test_edge_cases(review_service):
    """測試邊界情況"""
    # 測試空的歷史數據
    minimal_user_data = {"user_id": "test_123"}
    empty_history = []

    result = review_service.generate_review(
        user_data=minimal_user_data,
        history_data=empty_history
    )
    assert isinstance(result["analysis"], str)

    # 測試最小用戶數據
    progress_result = review_service.analyze_progress(
        user_data=minimal_user_data,
        history_data=empty_history
    )
    assert isinstance(progress_result["progress_analysis"], str)

if __name__ == "__main__":
    # 手動測試示例
    review_service = ReviewService()

    # 準備測試數據
    user_data = {
        "user_id": "test_user_123",
        "name": "測試用戶",
        "level": "intermediate",
        "focus_areas": ["python", "machine_learning"]
    }

    history_data = [
        {
            "date": "2024-03-01",
            "activity": "專案完成",
            "metrics": {
                "quality": 8.5,
                "efficiency": 7.8
            }
        }
    ]

    # 測試生成回饋
    print("\n=== 測試生成回饋 ===")
    review_result = review_service.generate_review(
        user_data=user_data,
        history_data=history_data,
        review_type="monthly"
    )
    print(f"回饋結果：\n{json.dumps(review_result, ensure_ascii=False, indent=2)}")

    # 測試進度分析
    print("\n=== 測試進度分析 ===")
    progress_result = review_service.analyze_progress(
        user_data=user_data,
        history_data=history_data,
        specific_aspects=["python", "machine_learning"]
    )
    print(f"進度分析結果：\n{json.dumps(progress_result, ensure_ascii=False, indent=2)}")
