from sqlalchemy import Column, Integer, String, Text, ARRAY, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base  # 引用分離出的 Base


# 資格模型
class Eligibility(Base):
    __tablename__ = 'eligibility'

    id = Column(Integer, primary_key=True)
    reference_file_path = Column(Text)
    partner_emails = Column(ARRAY(Text))  # 使用 array 儲存陣列
    fee_plans_id = Column(Integer, ForeignKey('fee_plans.id'))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    fee_plan = relationship("FeePlan", back_populates="eligibilities")