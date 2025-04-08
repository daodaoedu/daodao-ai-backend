from sqlalchemy import Column, Integer, String, Date, TIMESTAMP, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from .base import Base


class Post(Base):
    __tablename__ = 'post'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    type = Column(String(20), nullable=False)
    week = Column(Integer)
    title = Column(String(255), nullable=False)
    date = Column(Date)
    visibility = Column(String(10), default='private')
    status = Column(String(20), default='draft')
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    # 在 Post 模型中延遲導入
    project = relationship("Project", back_populates="posts", lazy="joined")
    user = relationship("User", back_populates="posts", lazy="joined")
    
    __table_args__ = (
        CheckConstraint("type IN ('outcome', 'note', 'review')", name='check_post_type'),
        CheckConstraint("visibility IN ('public', 'private')", name='check_visibility'),
        CheckConstraint("status IN ('draft', 'published')", name='check_status'),
    )