from sqlalchemy import Column, Integer,TIMESTAMP, String, Text, Date, Boolean, Time, ForeignKey, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base  # 引用分離出的 Base
from utils.code_enum import partnerEducationStep_t, group_type_t, group_category_t

class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True)
    title = Column(Text)
    photo_url = Column('photo_url', String(255))
    photo_alt = Column('photo_alt',String(255))
    category = Column(ARRAY(group_category_t))
    
    group_type = Column(ARRAY(group_type_t))
    partner_education_step = Column('partner_education_step', ARRAY(partnerEducationStep_t))
    
    description = Column(String(255))
    city_id = Column(Integer)
    is_grouping = Column('is_grouping', Boolean)
    createdDate = Column('created_date', TIMESTAMP(timezone=False), nullable=False)
    updatedDate = Column('updated_date', TIMESTAMP(timezone=False), nullable=False)
    time = Column(Text)
    partner_style = Column('partner_style', Text)
    tag_list = Column('tag_list', ARRAY(String))
    
    created_at = Column(Date, default=func.now())
    created_by = Column(Integer, ForeignKey('users.id'))
    
    updated_at = Column(Date)
    updated_by = Column(String(255))
    
    motivation = Column(Text)
    contents = Column(Text)
    expectation_result = Column(Text)
    notice  = Column(Text)
    group_deadline = Column('group_deadline', TIMESTAMP(timezone=False), nullable=False)
    
    is_need_deadline = Column("is_need_deadline", Boolean)
    participator = Column("participator", Integer)
    hold_time = Column(Time)
    is_online = Column(Boolean)
    TBD = Column(Boolean)
    
    # Relationships
    created_by_user = relationship("User", back_populates="groups_created")
    user_join_group = relationship("UserJoinGroup", back_populates="group")
    
    def __repr__(self):
        return f"<Group(id={self.id}, title={self.title})>"