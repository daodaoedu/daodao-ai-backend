from sqlalchemy import String, Column, Integer, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from datetime import datetime
import uuid

from .base import Base  # 引用分離出的 Base



class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    major_category_id = Column(Integer, ForeignKey("categories.id"))
    sub_category_id = Column(Integer, ForeignKey("categories.id"))
    name = Column(String(255), nullable=False)
    url = Column(String(1000), nullable=False)
    image_url = Column(String(1000))
    description = Column(Text, nullable=False)
    video_url = Column(String(1000))
    type = Column(String(100), nullable=False)
    cost = Column(String(50), nullable=False)
    level = Column(String(50), default="all_levels", nullable=False)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime)
    deleted_at = Column(DateTime)

    creator = relationship("User", back_populates="resource")  # 若有對應 User Model

