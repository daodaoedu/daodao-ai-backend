from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.dependencies import AdminDep, SessionDep
from src.models.AIServiceConfig import AIServiceConfig
from src.response_template import api_response_decorator
from src.schemas.admin.ai_service_config import (
    AIServiceConfigCreate,
    AIServiceConfigRead,
    AIServiceConfigUpdate,
)

router = APIRouter()


@router.get("/ai-service-configs")
@api_response_decorator
def list_ai_service_configs(
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    service: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """列出 AI service configs（可依 service 篩選）。"""
    query = db.query(AIServiceConfig)
    if service is not None:
        query = query.filter(AIServiceConfig.service == service)

    total = query.count()
    configs = (
        query.order_by(AIServiceConfig.id.desc()).offset(offset).limit(limit).all()
    )
    data: List[AIServiceConfigRead] = [
        AIServiceConfigRead.model_validate(c) for c in configs
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


@router.get("/ai-service-configs/{config_id}")
@api_response_decorator
def get_ai_service_config(
    config_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    config = db.query(AIServiceConfig).filter(AIServiceConfig.id == config_id).first()
    if not config:
        raise HTTPException(
            status_code=404, detail=f"AIServiceConfig {config_id} not found"
        )
    return {
        "data": AIServiceConfigRead.model_validate(config).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }


@router.post("/ai-service-configs")
@api_response_decorator
def create_ai_service_config(
    body: AIServiceConfigCreate,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """建立新 AI service config。is_active=True 時自動 deactivate 同 service 其他 configs。"""
    if body.is_active:
        db.query(AIServiceConfig).filter(
            AIServiceConfig.service == body.service,
            AIServiceConfig.is_active == True,  # noqa: E712
        ).update({"is_active": False})

    config = AIServiceConfig(
        service=body.service,
        name=body.name,
        model_id=body.model_id,
        system_prompt_id=body.system_prompt_id,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        top_p=body.top_p,
        top_k=body.top_k,
        is_active=body.is_active,
        notes=body.notes,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return {
        "data": AIServiceConfigRead.model_validate(config).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }


@router.put("/ai-service-configs/{config_id}")
@api_response_decorator
def update_ai_service_config(
    config_id: int,
    body: AIServiceConfigUpdate,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """更新 AI service config。is_active=True 時自動 deactivate 同 service 其他 configs。"""
    config = db.query(AIServiceConfig).filter(AIServiceConfig.id == config_id).first()
    if not config:
        raise HTTPException(
            status_code=404, detail=f"AIServiceConfig {config_id} not found"
        )

    if body.name is not None:
        config.name = body.name
    if body.model_id is not None:
        config.model_id = body.model_id
    if body.system_prompt_id is not None:
        config.system_prompt_id = body.system_prompt_id
    if body.max_tokens is not None:
        config.max_tokens = body.max_tokens
    if body.temperature is not None:
        config.temperature = body.temperature
    if body.top_p is not None:
        config.top_p = body.top_p
    if body.top_k is not None:
        config.top_k = body.top_k
    if body.notes is not None:
        config.notes = body.notes

    if body.is_active is not None:
        if body.is_active and not config.is_active:
            db.query(AIServiceConfig).filter(
                AIServiceConfig.service == config.service,
                AIServiceConfig.id != config_id,
                AIServiceConfig.is_active == True,  # noqa: E712
            ).update({"is_active": False})
        config.is_active = body.is_active

    db.commit()
    db.refresh(config)
    return {
        "data": AIServiceConfigRead.model_validate(config).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }


@router.delete("/ai-service-configs/{config_id}")
@api_response_decorator
def delete_ai_service_config(
    config_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    config = db.query(AIServiceConfig).filter(AIServiceConfig.id == config_id).first()
    if not config:
        raise HTTPException(
            status_code=404, detail=f"AIServiceConfig {config_id} not found"
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


@router.post("/ai-service-configs/{config_id}/activate")
@api_response_decorator
def activate_ai_service_config(
    config_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """將指定 config 設為 active，並 deactivate 同 service 其他 configs。"""
    config = db.query(AIServiceConfig).filter(AIServiceConfig.id == config_id).first()
    if not config:
        raise HTTPException(
            status_code=404, detail=f"AIServiceConfig {config_id} not found"
        )

    db.query(AIServiceConfig).filter(
        AIServiceConfig.service == config.service,
        AIServiceConfig.id != config_id,
        AIServiceConfig.is_active == True,  # noqa: E712
    ).update({"is_active": False})

    config.is_active = True
    db.commit()
    db.refresh(config)
    return {
        "data": AIServiceConfigRead.model_validate(config).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }
