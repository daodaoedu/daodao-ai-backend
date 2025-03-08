# 用戶身份聯接表
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base  # 引用分離出的 Base


class UserPosition(Base):
    __tablename__ = 'user_positions'

    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    position_id = Column(Integer, ForeignKey('position.id', ondelete='CASCADE'), primary_key=True)

    user = relationship("User", backref="user_positions")
    position = relationship("Position", backref="user_positions")