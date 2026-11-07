import os

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from src.config import JWT_SECRET_PLACEHOLDERS, get_settings, is_unconfigured_secret
from src.logger import AppLogger

logger = AppLogger(__name__).get_logger()


def verify(token: str):
    secret = get_settings().jwt_security
    if is_unconfigured_secret(secret, JWT_SECRET_PLACEHOLDERS):
        logger.warning("JWT verification is unavailable: signing secret not configured")
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except ExpiredSignatureError:
        logger.info("Token 已過期")
    except InvalidTokenError:
        logger.info("無效的 Token")

    return None


if __name__ == "__main__":
    test_token = os.getenv("MY_TOKEN_ID", "test")

    verify(test_token)
