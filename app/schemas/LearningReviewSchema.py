from pydantic import BaseModel


class LearningReviewSchema(BaseModel):
    post_id: int
    content: str

    class Config:
        orm_mode = True
