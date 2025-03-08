from sqlalchemy import Column, Integer, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base  # 引用分離出的 Base
from sqlalchemy.dialects.postgresql import ENUM

class UserJoinGroup(Base):
    __tablename__ = 'user_join_group'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    group_id = Column(Integer, ForeignKey('groups.id'))
    
    group_participation_role_t = Column(ENUM('Initiator', 'Member', 'Other', name='group_participation_role_t'), default='Initiator')
    participated_at = Column(TIMESTAMP, default=func.now())

    # Relationships
    user = relationship("User", back_populates="user_join_group")
    group = relationship("Group", back_populates="user_join_group")

    def __repr__(self):
        return f"<UserJoinGroup(user_id={self.user_id}, group_id={self.group_id})>"
