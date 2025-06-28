from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Review, Post, Resource, User, Category
from schemas.resource import TopReviewOut, TopContributorOut, TopCategoryOut


def get_popular_resources(db: Session, limit: int = 10):
    # 如何定義最熱門
    return db.query(Resource).filter(Resource.status == 'active')\
        .order_by(Resource.created_at.desc()).limit(limit).all()

def get_latest_resources(db: Session, limit: int = 10):
    return db.query(Resource).filter(Resource.status == 'active')\
        .order_by(Resource.created_at.desc()).limit(limit).all()

def get_recommended_resources(db: Session, user_id: int, limit: int = 10):
    # 根據 user_id 查喜好、收藏或分類偏好（需自定義）
    return db.query(Resource).filter(Resource.status == 'active')\
        .order_by(Resource.created_at.desc()).limit(limit).all()

# 其他如 熱門分類、活躍使用者、熱門心得 會需要 JOIN 其他表設計

def get_top_reviews_data(db: Session, limit: int = 10) -> list[TopReviewOut]:
    results = (
        db.query(
            Review.id.label("review_id"),
            Review.learning_review,
            Review.learning_feedback,
            Review.created_at,
            Resource.id.label("resource_id"),
            Resource.name.label("resource_name"),
            Resource.url.label("resource_url")
        )
        .join(Post, Review.post_id == Post.id)
        .join(Resource, Post.project_id == Resource.id)  # 若你的 Post 有 resource_id 請改成 Post.resource_id
        .filter(Review.visibility == 'public')
        .order_by(Review.learning_review.desc(), Review.created_at.desc())
        .limit(limit)
        .all()
    )

    return [TopReviewOut(**r._asdict()) for r in results]


def get_top_contributors(db: Session, limit: int = 10) -> list[TopContributorOut]:
    results = (
        db.query(
            User.id,
            User.nickname,
            func.count(Resource.id).label("resource_count")
        )
        .join(Resource, Resource.created_by == User.id)
        .filter(Resource.status == "active")
        .group_by(User.id)
        .order_by(func.count(Resource.id).desc())
        .limit(limit)
        .all()
    )

    return [TopContributorOut(**r._asdict()) for r in results]


def get_top_categories(db: Session, limit: int = 10) -> list[TopCategoryOut]:
    results = (
        db.query(
            Category.id,
            Category.name,
            func.count(Resource.id).label("resource_count")
        )
        .join(Resource, Resource.major_category_id == Category.id)
        .filter(Resource.status == "active")
        .group_by(Category.id)
        .order_by(func.count(Resource.id).desc())
        .limit(limit)
        .all()
    )

    return [TopCategoryOut(**r._asdict()) for r in results]

