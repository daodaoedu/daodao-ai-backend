from sqlalchemy import Column, Integer, String, Text, ForeignKey, ARRAY, Boolean, TIMESTAMP, Date, Enum, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base
from utils.code_enum import motivation_t, strategy_t, outcome_t
import uuid

class Project(Base):
    __tablename__ = 'project'

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    img_url = Column(String(255))
    title = Column(String(255))
    description = Column(Text)
    motivation = Column(ARRAY(motivation_t))
    motivation_description = Column(Text)
    goal = Column(String(255))
    content = Column(Text)
    strategy = Column(ARRAY(strategy_t))
    strategy_description = Column(Text)
    # resource_name = Column(ARRAY(Text))
    # resource_url = Column(ARRAY(Text))
    # 這邊之後要跟找資源的resource資料表串一起
    resource = Column(Text)
    outcome = Column(ARRAY(outcome_t))
    outcome_description = Column(Text)
    is_public = Column(Boolean, default=False)
    status = Column(Enum('Ongoing', 'Completed', 'Not Started', 'Canceled'), default='Not Started')
    start_date = Column(Date)
    end_date = Column(Date)
    interval = Column(Integer)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')
    created_by = Column(Integer)
    updated_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP', onupdate='CURRENT_TIMESTAMP')
    updated_by = Column(Integer)
    version = Column(Integer)

    __table_args__ = (
        CheckConstraint("start_date < end_date", name="check_start_date_end_date"),
        CheckConstraint("interval > 0", name="check_interval_positive"),
        UniqueConstraint("user_id", "title", "version", name="uq_user_project_version"),
    )

    milestones = relationship("Milestone", back_populates="project")
    tasks = relationship("Task", secondary="milestone", back_populates="project")

