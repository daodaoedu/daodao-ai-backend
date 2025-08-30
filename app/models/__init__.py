import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .AIReviewFeedback import AIReviewFeedback
from .base import Base  # 導出 Base 供其他代碼使用
from .BasicInfo import BasicInfo
from .City import City
from .Comment import Comment
from .Contact import Contact
from .Country import Country
from .Eligibility import Eligibility
from .FeePlan import FeePlan
from .Group import Group
from .Location import Location
from .Marathon import Marathon
from .MentorParticipants import MentorParticipants
from .Milestone import Milestone
from .Outcome import Outcome
from .Position import Position
from .Post import Post
from .Project import Project
from .ProjectMarathon import ProjectMarathon
from .Resource import Resource
from .Review import Review
from .Store import Store
from .Task import Task
from .User import User  # 將 Store 類別定義放在 User 類別之前
from .UserJoinGroup import UserJoinGroup
from .UserPosition import UserPosition
from .UserProfile import UserProfile
from .UserProject import UserProject

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("請設定環境變數 DATABASE_URL 為 PostgreSQL 連線字串")
engine = create_engine(
    f"{os.getenv('DATABASE_URL')}", pool_size=5, pool_timeout=10, echo=False
)  # echo=True for debug

# 創建 Session 類別
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 導出所有類別
__all__ = [
    "User",
    "Contact",
    "BasicInfo",
    "Location",
    "Country",
    "City",
    "Base",
    "Store",
    "Resource",
    "Position",
    "UserPosition",
    "Group",
    "UserJoinGroup",
    "Project",
    "Milestone",
    "Marathon",
    "Task",
    "UserProject",
    "FeePlan",
    "Eligibility",
    "ProjectMarathon",
    "UserProfile",
    "MentorParticipants",
    "Comment",
    "Review",
    "AIReviewFeedback",
    "Post",
    "Outcome",
    "Category",
]


def get_db():

    db = Session()
    try:
        yield db
    finally:
        db.close()
