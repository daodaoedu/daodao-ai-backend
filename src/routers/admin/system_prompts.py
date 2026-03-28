from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.dependencies import AdminDep, SessionDep
from src.models.SystemPrompt import SystemPrompt
from src.response_template import api_response_decorator
from src.schemas.admin.system_prompt import (
    SystemPromptCreate,
    SystemPromptRead,
    SystemPromptUpdate,
)
from src.services.admin.prompt_service import deactivate_others

router = APIRouter()


@router.get("/system-prompts")
@api_response_decorator
def list_system_prompts(
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    is_active: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """列出 system prompts（可依 is_active 篩選）。"""
    query = db.query(SystemPrompt)
    if is_active is not None:
        query = query.filter(SystemPrompt.is_active == is_active)

    total = query.count()
    prompts = query.order_by(SystemPrompt.id.desc()).offset(offset).limit(limit).all()
    data: List[SystemPromptRead] = [SystemPromptRead.model_validate(p) for p in prompts]
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


@router.get("/system-prompts/{prompt_id}")
@api_response_decorator
def get_system_prompt(
    prompt_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    prompt = db.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(
            status_code=404, detail=f"SystemPrompt {prompt_id} not found"
        )
    return {
        "data": SystemPromptRead.model_validate(prompt).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }


@router.post("/system-prompts")
@api_response_decorator
def create_system_prompt(
    body: SystemPromptCreate,
    admin: AdminDep,
    db: SessionDep,
) -> dict:
    """建立新 system prompt。is_active=True 時自動 deactivate 其他所有 prompt。"""
    if db.query(SystemPrompt).filter(SystemPrompt.name == body.name).first():
        raise HTTPException(
            status_code=409, detail=f"System prompt name '{body.name}' already exists"
        )

    if body.is_active:
        deactivate_others(db)

    prompt = SystemPrompt(
        name=body.name,
        content=body.content,
        is_active=body.is_active,
        version=1,
        created_by=admin.id,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return {
        "data": SystemPromptRead.model_validate(prompt).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }


@router.put("/system-prompts/{prompt_id}")
@api_response_decorator
def update_system_prompt(
    prompt_id: int,
    body: SystemPromptUpdate,
    admin: AdminDep,
    db: SessionDep,
) -> dict:
    """更新 system prompt。content 有變更時 version +1。"""
    prompt = db.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(
            status_code=404, detail=f"SystemPrompt {prompt_id} not found"
        )

    if body.name and body.name != prompt.name:
        if db.query(SystemPrompt).filter(SystemPrompt.name == body.name).first():
            raise HTTPException(
                status_code=409,
                detail=f"System prompt name '{body.name}' already exists",
            )
        prompt.name = body.name

    if body.content is not None and body.content != prompt.content:
        prompt.content = body.content
        prompt.version = (prompt.version or 1) + 1

    if body.is_active is not None:
        if body.is_active and not prompt.is_active:
            deactivate_others(db, exclude_id=prompt_id)
        prompt.is_active = body.is_active

    prompt.updated_by = admin.id
    db.commit()
    db.refresh(prompt)
    return {
        "data": SystemPromptRead.model_validate(prompt).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }


@router.delete("/system-prompts/{prompt_id}")
@api_response_decorator
def delete_system_prompt(
    prompt_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    prompt = db.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(
            status_code=404, detail=f"SystemPrompt {prompt_id} not found"
        )
    db.delete(prompt)
    db.commit()
    return {
        "data": {"deleted": True, "id": prompt_id},
        "pagination": None,
        "cache_hit": False,
    }
