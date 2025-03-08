from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from utils.code_enum import qualifications_t

from .base import Base  # 引用分離出的 Base

# 收費計劃模型
class FeePlan(Base):
    __tablename__ = 'fee_plans'

    id = Column(Integer, primary_key=True)
    fee_plan_type = Column(qualifications_t)  # 假設 qualifications_t 是 String 類型
    name = Column(String(255))
    discount = Column(Numeric(8, 2))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    eligibilities = relationship("Eligibility", back_populates="fee_plan")
