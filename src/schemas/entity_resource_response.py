from datetime import date, datetime
from typing import List, Optional, Union

from pydantic import BaseModel


# -------------------------------
# 🧍 使用者基本資訊
# -------------------------------
class UserBasicInfo(BaseModel):
    id: int
    name: str
    photo_url: Optional[str] = None
    tag_list: Optional[List[str]] = []
    share_list: Optional[List[str]] = []


# -------------------------------
# 📊 共通互動統計
# -------------------------------
class InteractionStats(BaseModel):
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    view_count: int = 0


# -------------------------------
# 🧱 基礎貼文結構
# -------------------------------
class BasePost(BaseModel):
    id: str
    type: str  # idea / practice / project
    title: Optional[str]
    content: Optional[str]
    tags: List[
        str
    ] = (
        []
    )  # ideas not tags so far, practices leverage custom_content_type, project leverage strategy, motivation, outcome
    user: UserBasicInfo
    status: str = "active"
    stats: InteractionStats
    created_at: datetime
    updated_at: Optional[datetime]
    # has_resources: bool # if yes, search entity_resource to get resource_id list , and get resource info(url and name) from resource table
    resources: Optional[
        dict
    ]  # {reource_name: resource_url} search entity_resource to get resource_id list , and get resource info(url and name) from resource table


# -------------------------------
# 💡 想法 Idea 貼文
# -------------------------------
class IdeaPost(BasePost):
    type: str = "idea"
    # 想法沒有額外欄位


# -------------------------------
# 🏃 實踐 Practice 貼文
# -------------------------------
class DailyGoal(BaseModel):
    type: str  # time / count
    time_minutes: Optional[int]
    count: Optional[int]


class PracticePost(BasePost):
    type: str = "practice"
    total_amount: int
    current_progress: int
    start_date: Optional[date]
    daily_goal: DailyGoal
    streak: int
    max_streak: int
    last_checkin_date: Optional[date]
    has_resources: bool = False
    content_type: Optional[str]
    custom_content_type: Optional[str]


# -------------------------------
# 🏗️ 專案 Project 貼文
# -------------------------------
class Milestone(BaseModel):
    title: str
    description: Optional[str]
    target_date: Optional[date]
    completed: bool = False


class ProjectPost(BasePost):
    type: str = "project"
    description: Optional[str]
    motivation_description: Optional[str]
    goal: Optional[str]
    strategy_description: Optional[str]
    outcome_description: Optional[str]
    milestones: List[Milestone] = []


# -------------------------------
# 🔍 詳細模式回傳
# -------------------------------
PostDetail = Union[IdeaPost, PracticePost, ProjectPost]
