# 用戶身份聯接表
from sqlalchemy import Column, Integer,  Text, ForeignKey, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
import uuid
from .base import Base  # 引用分離出的 Base




class ProjectMarathon(Base):
    __tablename__ = "project_marathon"
    __table_args__ = (
        UniqueConstraint("project_id", "marathon_id", name="unique_project_marathon"),  # 唯一約束
    )

    id = Column(Integer, primary_key=True, autoincrement=True, unique=True, comment="主鍵")
    project_id = Column(Integer, ForeignKey("project.id", ondelete="CASCADE"), nullable=False, comment="專案 ID，指向 project 表的 id")
    marathon_id = Column(Integer, ForeignKey("marathon.id", ondelete="CASCADE"), nullable=False, comment="馬拉松 ID，指向 marathon 表的 id")
    eligibility_id = Column(Integer, ForeignKey("eligibility.id"), nullable=True, comment="收費計劃")
    project_registration_date = Column(TIMESTAMP, default="now()", comment="專案報名此馬拉松的日期")
    status = Column(ENUM('Pending', 'Approved', 'Rejected'), nullable=False, comment="專案報名的審核狀態")
    

    feedback = Column(Text, comment="評審意見或備註")
    created_at = Column(TIMESTAMP, default="now()", comment="建立時間")
    updated_at = Column(TIMESTAMP, default="now()", onupdate="now()", comment="更新時間")