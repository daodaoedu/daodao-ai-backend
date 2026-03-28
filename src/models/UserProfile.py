from sqlalchemy import (
    ARRAY,
    TIMESTAMP,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB  # 修正為正確的引入方式
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.models.base import Base  # 引用分離出的 Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    nickname = Column(String(100))
    bio = Column(Text)
    skills = Column(ARRAY(Text))  # 用 TEXT[] 陣列類型，根據 PostgreSQL 需要進行處理
    interests = Column(ARRAY(Text))  # 用 TEXT[] 陣列類型，根據 PostgreSQL 需要進行處理
    learning_needs = Column(
        ARRAY(Text)
    )  # 用 TEXT[] 陣列類型，根據 PostgreSQL 需要進行處理
    contact_info = Column(JSONB)
    is_public = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # 關聯到 User 模型
    user = relationship("User", back_populates="profile")

    def __repr__(self):
        return f"<UserProfile(id={self.id}, user_id={self.user_id}, nickname={self.nickname})>"
