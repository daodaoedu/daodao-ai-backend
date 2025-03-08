from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from .base import Base  # 引用分離出的 Base



class Location(Base):
    __tablename__ = "location"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False, unique=True)
    city_id = Column(Integer, ForeignKey("city.id"), nullable=True)
    country_id = Column(Integer, ForeignKey("country.id"), nullable=True)
    isTaiwan = Column(Boolean, nullable=True)

    # 與 City 建立一對一關聯
    city = relationship("City", back_populates="locations")
    # 與 user 關聯
    user = relationship("User", back_populates="location")
    # 
    country = relationship("Country", back_populates="locations")
