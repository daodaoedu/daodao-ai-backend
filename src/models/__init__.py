# models/__init__.py
from sqlalchemy.orm import Session

from src.models.base import Base  # 導出 Base 供其他代碼使用

from .AIReviewFeedback import AIReviewFeedback
from .BasicInfo import BasicInfo
from .City import City
from .Comment import Comment
from .Contact import Contact
from .Country import Country
from .Eligibility import Eligibility
from .EntityResource import EntityResource
from .EntityTag import EntityTag
from .FeePlan import FeePlan
from .Group import Group
from .Idea import Idea
from .Location import Location
from .Marathon import Marathon
from .MentorParticipants import MentorParticipants
from .Milestone import Milestone
from .Outcome import Outcome
from .Position import Position
from .Post import Post
from .Practice import Practice
from .PracticeCheckIn import PracticeCheckIn
from .Project import Project
from .ProjectMarathon import ProjectMarathon
from .Resource import Resource
from .Review import Review
from .Store import Store
from .Tag import Tag
from .Task import Task
from .User import User  # 將 Store 類別定義放在 User 類別之前
from .UserJoinGroup import UserJoinGroup
from .UserPosition import UserPosition
from .UserProfile import UserProfile
from .UserProject import UserProject
from .Category import Category

#

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
    "PracticeCheckIn",
    "Practice",
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
    "Idea",
    "EntityResource",
    "EntityTag",
    "Tag",
]


def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()
