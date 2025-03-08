from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from .base import Base  # 引用分離出的 Base

class Country(Base):
    __tablename__ = "country"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alpha2 = Column(String(2))
    alpha3 = Column(String(3) )
    name = Column(String(100), nullable=False)
    
    
    locations = relationship("Location", back_populates="country") 

    def __repr__(self):
        return f"<Country(id={self.id}, alpha2='{self.alpha2}', alpha3='{self.alpha3}', name='{self.name}')>"