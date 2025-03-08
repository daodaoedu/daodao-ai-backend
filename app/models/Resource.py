from sqlalchemy import create_engine, Column, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from utils.code_enum import cost_t, age_t
from .base import Base  # 引用分離出的 Base



class Resource(Base):
    __tablename__ = 'resource'
    id = Column(Integer, primary_key=True)
    created_by_user_id = Column(Integer, ForeignKey('users.id'), unique=True)
    image_url = Column(Text)
    resource_name = Column(Text) 
    cost = Column(cost_t) # TODO, index to filter
    tag_list = Column(Text) # TODO 標籤 split(,) index to filter
    username = Column(Text)
    age = Column(age_t) # TODO split(,) index to filter
    type_list = Column(Text) # TODO, 資源類型 split(,) index to filter
    url_link = Column(Text)
    filed_name_list = Column(Text)  # TODO, 領域名稱 split(,) index to filter
    video_url = Column(Text)
    introduction = Column(Text)
    area = Column(Text)
    supplement = Column(Text)

    user = relationship("User", back_populates="resource")
