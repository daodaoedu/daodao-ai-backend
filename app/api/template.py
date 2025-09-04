from functools import wraps
from fastapi import HTTPException
from typing import Callable, Any, Coroutine, Dict
from logger import AppLogger
from api.schemas.api_response import (
    APIResponse,
    build_success_response,
    build_error_response
)
import inspect



logger = AppLogger(__name__).get_logger()

def api_response_decorator(func: Callable[..., Coroutine[Any, Any, Any]]):
    """統一 API 回傳格式的裝飾器"""
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Dict:
        try:
            # 判斷函數是否為 coroutine
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            # logger.info(f"{func.__name__} result: {result}")

            # 如果已經是 APIResponse 或 dict 含 success key，直接返回
            if isinstance(result, APIResponse):
                return result.dict()
            if isinstance(result, dict) and "success" in result:
                return result

            # 否則包裝成 success response
            return build_success_response(data=result)

        except HTTPException as e:
            return build_error_response(
                code="HTTP_ERROR",
                message=e.detail,
                details={"status_code": e.status_code}
            )
        except Exception as e:
            return build_error_response(
                code="INTERNAL_ERROR",
                message=str(e),
            )

    return wrapper
