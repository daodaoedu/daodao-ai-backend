from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from .Contact import Contact
from .BasicInfo import BasicInfo
from .Location import Location
from .City import City
from .base import Base  # 導出 Base 供其他代碼使用
from .Store import Store
from .Resource import Resource
from .Position import Position
from .UserPosition import UserPosition
from .User import User # 將 Store 類別定義放在 User 類別之前
from .Group import Group
from .UserJoinGroup import UserJoinGroup
from .Project import Project
from .Marathon import Marathon
from .Milestone import Milestone
from .Task import Task
from .UserProject import UserProject
from .FeePlan import FeePlan
from .Eligibility import Eligibility
from .ProjectMarathon import ProjectMarathon
from .UserProfile import UserProfile
from .Country import Country
from .MentorParticipants import MentorParticipants
from .Comment import Comment
from .Review import Review
from .AIReviewFeedback import AIReviewFeedback
from .Post import Post
from .Outcome import Outcome

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("請設定環境變數 DATABASE_URL 為 PostgreSQL 連線字串")
engine = create_engine(
    "postgresql+psycopg2://daodao:daodao@postgres-daodao:5432/daodao", pool_size=5, pool_timeout=10, echo=False
)  # echo=True for debug

# 創建 Session 類別
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 導出所有類別
__all__ = [ "User", "Contact", "BasicInfo", "Location", "Country", "City", "Base",
           "Store", "Resource", "Position", "UserPosition", "Group", "UserJoinGroup",
           "Project", "Milestone", "Marathon", "Task", "UserProject",
           "FeePlan","Eligibility", "ProjectMarathon", "UserProfile",
           "MentorParticipants",
           "Comment", "Review", "AIReviewFeedback", "Post", "Outcome"
           ]

def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()
