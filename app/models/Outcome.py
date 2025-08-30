from sqlalchemy import ARRAY, TIMESTAMP, Column, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class Outcome(Base):
    __tablename__ = "outcome"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("post.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text)
    image_urls = Column(ARRAY(Text))
    video_urls = Column(ARRAY(Text))
    visibility = Column(String(10), default="private")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
