from pydantic import BaseModel


class FeedbackSchema(BaseModel):
    review_id: int
    content: str

    class Config:
        orm_mode = True
