from sqlalchemy import (
    Column, Integer, String, Text, SmallInteger, ForeignKey, TIMESTAMP, CheckConstraint, func
)
from sqlalchemy.orm import relationship
from models import Base


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String(20), nullable=False)
    target_id = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    visibility = Column(String(10), default="private")

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # 外鍵關聯
    user = relationship("User", back_populates="comments")

    # 限制 target_type 和 visibility
    __table_args__ = (
        CheckConstraint(target_type.in_(['post', 'resource', 'note', 'outcome', 'review', 'circle', 'idea', 'portfolio'])),
        CheckConstraint(visibility.in_(['public', 'private'])),
    )