from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from .base import Base  # 引用分離出的 Base


# 定義 Position 類型
class Position(Base):
    __tablename__ = "position"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)

    # 與 UserPosition 關聯
    user_positions = relationship("UserPosition", back_populates="position")
    users = association_proxy("user_positions", "user")

    def __repr__(self):
        return f"<Position(id={self.id}, name='{self.name}')>"
