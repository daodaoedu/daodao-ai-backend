from sqlalchemy import Column, Integer, ForeignKey
from .base import Base

class MentorParticipants(Base):
    __tablename__ = 'mentor_participants'
    
    mentor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, comment="指向 users 表中 role_id = 4 (Mentor) 的 id。")
    participant_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, comment="指向 users 表中 role_id = 3 (Participant) 的 id。")

    