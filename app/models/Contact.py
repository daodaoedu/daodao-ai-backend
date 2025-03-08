from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Text, Table, MetaData
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from .base import Base  # 引用分離出的 Base

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False, unique=True)
    google_id = Column(String(255), nullable=True)
    photo_url = Column(String, nullable=True)
    is_subscribe_email = Column(Boolean, nullable=True)
    email = Column(String(255), nullable=True)
    ig = Column(String(255), nullable=True)
    discord = Column(String(255), nullable=True)
    line = Column(String(255), nullable=True)
    fb = Column(String(255), nullable=True)

    # 與 user 關聯
    user = relationship("User", back_populates="contact")
