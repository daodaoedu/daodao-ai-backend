import inspect
import time
from functools import wraps
from typing import Any, Callable, Coroutine, Dict

from fastapi import HTTPException
from logger import AppLogger
from schemas.api_response import (
    APIResponse,
    build_error_response,
    build_success_response,
)

logger = AppLogger(__name__).get_logger()


def api_response_decorator(func: Callable[..., Coroutine[Any, Any, Any]]):
    """統一 API 回傳格式的裝飾器"""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> Dict:
        start_time = time.time()

        try:
            # 判斷函數是否為 coroutine
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            # logger.info(f"{func.__name__} result: {result}")
            processing_time = int((time.time() - start_time) * 1000)  # ms

            # case 1: 已經是 APIResponse
            if isinstance(result, APIResponse):
                return result.dict()

            # case 2: 已經是完整的 response 格式
            if isinstance(result, dict) and "success" in result:
                return result

            # # case 3: 一般 dict（自動 merge 成完整結構）
            # if isinstance(result, dict):
            #     merged_data = {
            #         "success": True,
            #         "code": "SUCCESS",
            #         "message": "ok",
            #         "processing_time": processing_time,
            #         **result  # 直接展開原本 dict（例如 data、pagination、cache_hit）
            #     }
            #     return merged_data

            # case 4: 其他型別（list, str, obj...）
            return build_success_response(data=result, processing_time=processing_time)

        except HTTPException as e:
            return build_error_response(
                code="HTTP_ERROR",
                message=e.detail,
                details={"status_code": e.status_code},
            )
        except Exception as e:
            return build_error_response(
                code="INTERNAL_ERROR",
                message=str(e),
            )

    return wrapper
