import os

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from src.config import get_settings
from src.logger import AppLogger

logger = AppLogger(__name__).get_logger()

_PLACEHOLDER = "xxxxxxxxxxxxxxxx"


def verify(token: str):
    settings = get_settings()
    jwt_secret = settings.jwt_security

    if not jwt_secret or jwt_secret == _PLACEHOLDER:
        logger.error("JWT_SECURITY 未正確設定，拒絕驗證所有 token")
        return None

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        logger.debug(f"驗證成功，user_id:{payload.get('_id') or payload.get('id')}")
        return payload
    except ExpiredSignatureError:
        logger.info("Token 已過期")
    except InvalidTokenError:
        logger.warning("無效的 Token")


if __name__ == "__main__":
    test_token = os.getenv("MY_TOKEN_ID", "test")

    logger.info(f"Testing token: {test_token}")

    verify(test_token)
