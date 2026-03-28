import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.dependencies import AdminDep, CacheDep, SessionDep
from src.models.LLMModel import LLMModel
from src.response_template import api_response_decorator
from src.schemas.admin.llm_model import LLMModelCreate, LLMModelRead, LLMModelUpdate

router = APIRouter()

_MODELS_CACHE_KEY = "admin:llm_models:list"
_MODELS_TTL = 600  # 10 分鐘


def _invalidate_cache(cache: "CacheDep") -> None:
    try:
        cache.client.delete(_MODELS_CACHE_KEY)
    except Exception:
        pass


@router.get("/llm-models")
@api_response_decorator
def list_llm_models(
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    cache: CacheDep,
    provider: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
) -> dict:
    """列出 LLM model 設定（無篩選時使用 Redis 快取）。"""
    if provider is None and is_active is None:
        cached = cache.client.get(_MODELS_CACHE_KEY)
        if cached:
            return {"data": json.loads(cached), "pagination": None, "cache_hit": True}

    query = db.query(LLMModel)
    if provider:
        query = query.filter(LLMModel.provider == provider)
    if is_active is not None:
        query = query.filter(LLMModel.is_active == is_active)

    models = query.order_by(LLMModel.provider, LLMModel.model_name).all()
    data: List[LLMModelRead] = [LLMModelRead.model_validate(m) for m in models]
    payload = [d.model_dump(mode="json") for d in data]

    if provider is None and is_active is None:
        cache.client.set(
            _MODELS_CACHE_KEY, json.dumps(payload, default=str), ex=_MODELS_TTL
        )

    return {"data": payload, "pagination": None, "cache_hit": False}


@router.post("/llm-models")
@api_response_decorator
def create_llm_model(
    body: LLMModelCreate,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    cache: CacheDep,
) -> dict:
    existing = (
        db.query(LLMModel)
        .filter(
            LLMModel.provider == body.provider, LLMModel.model_name == body.model_name
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"LLMModel '{body.provider}/{body.model_name}' already exists",
        )

    model = LLMModel(**body.model_dump())
    db.add(model)
    db.commit()
    db.refresh(model)
    _invalidate_cache(cache)
    return {
        "data": LLMModelRead.model_validate(model).model_dump(mode="json"),
        "pagination": None,
        "cache_hit": False,
    }


@router.put("/llm-models/{model_id}")
@api_response_decorator
def update_llm_model(
    model_id: int,
    body: LLMModelUpdate,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    cache: CacheDep,
) -> dict:
    model = db.query(LLMModel).filter(LLMModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail=f"LLMModel {model_id} not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(model, field, value)

    db.commit()
    db.refresh(model)
    _invalidate_cache(cache)
    return {
        "data": LLMModelRead.model_validate(model).model_dump(mode="json"),
        "pagination": None,
        "cache_hit": False,
    }


@router.delete("/llm-models/{model_id}")
@api_response_decorator
def delete_llm_model(
    model_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    cache: CacheDep,
) -> dict:
    model = db.query(LLMModel).filter(LLMModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail=f"LLMModel {model_id} not found")
    db.delete(model)
    db.commit()
    _invalidate_cache(cache)
    return {
        "data": {"deleted": True, "id": model_id},
        "pagination": None,
        "cache_hit": False,
    }
