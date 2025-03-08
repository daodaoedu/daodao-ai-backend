from pydantic import BaseModel


class LearningReviewSchema(BaseModel):
    user_id: int
    content: str

    class Config:
        orm_mode = True