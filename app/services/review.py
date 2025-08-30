from models import Post, Review
from sqlalchemy.orm import Session


def get_review_trends(db: Session, project_id: int, current_review_id: int):
    review = db.query(Review).filter(Review.id == current_review_id).first()
    if not review:
        return []

    post_id = review.post_id
    reviews = (
        db.query(Review)
        .join(Post)
        .filter(
            Post.project_id == project_id, Post.type == "review", Post.id <= post_id
        )
        .order_by(Post.id.desc())
        .all()
    )
    return reviews
