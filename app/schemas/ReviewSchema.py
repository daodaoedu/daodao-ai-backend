from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ReviewSchema(BaseModel):
    post_id: int
    mood: str = Field(..., pattern="^(happy|calm|anxious|tired|frustrated)$")
    stress_level: int = Field(..., ge=1, le=10)
    learning_review: int = Field(..., ge=1, le=10)
    mood_description: Optional[str] = None
    learning_feedback: Optional[str] = None
    adjustment_plan: Optional[str] = None
    visibility: str = Field("private", pattern="^(public|private)$")
    
    class Config:
        from_attributes = True  