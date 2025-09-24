# from fastapi import APIRouter

# router = APIRouter(prefix="/v1/resources", tags=["resource"])


# 熱門心得 resource_review
# 活躍分享者
# 熱門分類

# 熱門資源
# @router.get("/popular", response_model=list[ResourceOut])
# def popular_resources(db: Session = Depends(get_db)):
#     return get_popular_resources(db)

# # 最新資源
# @router.get("/latest", response_model=list[ResourceOut])
# def latest_resources(db: Session = Depends(get_db)):
#     return get_latest_resources(db)

# # 推薦資源(有登入)
# @router.get("/recommended", response_model=list[ResourceOut])
# def recommended_resources(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):
#     return get_recommended_resources(db, current_user["id"])


# @router.get("/top-reviews")
# def top_reviews(db: Session = Depends(get_db)):
#     return get_top_reviews(db)

# @router.get("/top-contributors")
# def top_contributors(db: Session = Depends(get_db)):
#     return get_top_contributors(db)

# @router.get("/top-categories")
# def top_categories(db: Session = Depends(get_db)):
#     return get_top_categories(db)
