from typing import List

from fastapi import APIRouter, HTTPException, Query

from src.dependencies import AdminDep, SessionDep
from src.models.FeedRankingConfig import FeedRankingConfig
from src.response_template import api_response_decorator
from src.schemas.admin.feed_ranking_config import (
    FeedRankingConfigCreate,
    FeedRankingConfigRead,
    FeedRankingConfigUpdate,
)

router = APIRouter()


@router.get("/feed-ranking-configs")
@api_response_decorator
def list_feed_ranking_configs(
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """列出 feed 排序權重設定。"""
    query = db.query(FeedRankingConfig)
    total = query.count()
    configs = (
        query.order_by(FeedRankingConfig.id.desc()).offset(offset).limit(limit).all()
    )
    data: List[FeedRankingConfigRead] = [
        FeedRankingConfigRead.model_validate(c) for c in configs
    ]
    return {
        "data": [d.model_dump() for d in data],
        "pagination": {
            "total_count": total,
            "limit": limit,
            "offset": offset,
            "has_next": (offset + limit) < total,
        },
        "cache_hit": False,
    }


@router.get("/feed-ranking-configs/{config_id}")
@api_response_decorator
def get_feed_ranking_config(
    config_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    config = (
        db.query(FeedRankingConfig).filter(FeedRankingConfig.id == config_id).first()
    )
    if not config:
        raise HTTPException(
            status_code=404, detail=f"FeedRankingConfig {config_id} not found"
        )
    return {
        "data": FeedRankingConfigRead.model_validate(config).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }


@router.post("/feed-ranking-configs")
@api_response_decorator
def create_feed_ranking_config(
    body: FeedRankingConfigCreate,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """建立新 feed 排序權重設定。is_active=True 時自動 deactivate 其他 configs。"""
    if body.is_active:
        db.query(FeedRankingConfig).filter(
            FeedRankingConfig.is_active.is_(True)
        ).update({"is_active": False})

    config = FeedRankingConfig(
        name=body.name,
        w_social=body.w_social,
        w_engagement=body.w_engagement,
        w_content=body.w_content,
        w_decay=body.w_decay,
        w_freshness=body.w_freshness,
        freshness_window_hours=body.freshness_window_hours,
        w_featured=body.w_featured,
        is_active=body.is_active,
        notes=body.notes,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return {
        "data": FeedRankingConfigRead.model_validate(config).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }


@router.put("/feed-ranking-configs/{config_id}")
@api_response_decorator
def update_feed_ranking_config(
    config_id: int,
    body: FeedRankingConfigUpdate,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """更新 feed 排序權重設定。is_active=True 時自動 deactivate 其他 configs。"""
    config = (
        db.query(FeedRankingConfig).filter(FeedRankingConfig.id == config_id).first()
    )
    if not config:
        raise HTTPException(
            status_code=404, detail=f"FeedRankingConfig {config_id} not found"
        )

    if body.name is not None:
        config.name = body.name
    if body.w_social is not None:
        config.w_social = body.w_social
    if body.w_engagement is not None:
        config.w_engagement = body.w_engagement
    if body.w_content is not None:
        config.w_content = body.w_content
    if body.w_decay is not None:
        config.w_decay = body.w_decay
    if body.w_freshness is not None:
        config.w_freshness = body.w_freshness
    if body.freshness_window_hours is not None:
        config.freshness_window_hours = body.freshness_window_hours
    if body.w_featured is not None:
        config.w_featured = body.w_featured
    if body.notes is not None:
        config.notes = body.notes

    if body.is_active is not None:
        if body.is_active and not config.is_active:
            db.query(FeedRankingConfig).filter(
                FeedRankingConfig.id != config_id,
                FeedRankingConfig.is_active.is_(True),
            ).update({"is_active": False})
        config.is_active = body.is_active

    db.commit()
    db.refresh(config)
    return {
        "data": FeedRankingConfigRead.model_validate(config).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }


@router.delete("/feed-ranking-configs/{config_id}")
@api_response_decorator
def delete_feed_ranking_config(
    config_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    config = (
        db.query(FeedRankingConfig).filter(FeedRankingConfig.id == config_id).first()
    )
    if not config:
        raise HTTPException(
            status_code=404, detail=f"FeedRankingConfig {config_id} not found"
        )
    if config.is_active:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete the active config. Deactivate it first.",
        )
    db.delete(config)
    db.commit()
    return {
        "data": {"deleted": True, "id": config_id},
        "pagination": None,
        "cache_hit": False,
    }


@router.post("/feed-ranking-configs/{config_id}/activate")
@api_response_decorator
def activate_feed_ranking_config(
    config_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """將指定 config 設為 active，並 deactivate 其他 configs。"""
    config = (
        db.query(FeedRankingConfig).filter(FeedRankingConfig.id == config_id).first()
    )
    if not config:
        raise HTTPException(
            status_code=404, detail=f"FeedRankingConfig {config_id} not found"
        )

    db.query(FeedRankingConfig).filter(
        FeedRankingConfig.id != config_id,
        FeedRankingConfig.is_active.is_(True),
    ).update({"is_active": False})

    config.is_active = True
    db.commit()
    db.refresh(config)
    return {
        "data": FeedRankingConfigRead.model_validate(config).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }
