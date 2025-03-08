from sqlalchemy import  Column, Integer, String
from sqlalchemy.orm import relationship
from .base import Base  # 引用分離出的 Base
from utils.code_enum import city_t


class City(Base):
    __tablename__ = "city"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False, unique=True)
    name = Column("name", city_t, nullable=True)  # City_t 類型映射為 String

    # 與 location 建立一對多關聯
    locations = relationship("Location", back_populates="city")