from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, TIMESTAMP, ARRAY
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import relationship
from .base import Base
from utils.code_enum import day_t

class Task(Base):
    __tablename__ = "task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    milestone_id = Column(Integer, ForeignKey("milestone.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255))
    description = Column(Text)
    days_of_week = Column(ARRAY(day_t))
    is_completed = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')
    updated_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP', onupdate='CURRENT_TIMESTAMP')

    milestone = relationship("Milestone", back_populates="tasks")
    project = relationship("Project", secondary="milestone", back_populates="tasks")
