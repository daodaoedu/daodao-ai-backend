import os

import jwt  # pyjwt 的標準 import 名稱
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from logger import AppLogger

logger = AppLogger(__name__).get_logger()

JWT_SECURITY = os.getenv("JWT_SECURITY")
JWT_EXPIRATION = os.getenv("JWT_EXPIRATION")
security = HTTPBearer()


def verify(token: str):
    try:
        payload = jwt.decode(token, JWT_SECURITY, algorithms=["HS256"])
        logger.info("驗證成功，payload:", payload)
        return payload
    except ExpiredSignatureError:
        logger.info("Token 已過期")
    except InvalidTokenError:
        logger.info("無效的 Token")

    # {'id': 20, '_id': '2e', 'time': , 'isTemp': False, 'iat': 1756544897, 'exp': 1756566497}


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):

    # def get_current_user(authorization: Optional[str] = Header(None)):

    """
    FastAPI Dependency: 驗證 JWT 並回傳 payload
    """
    token = credentials.credentials  # 自動取 token，不用 Bearer 前綴
    return verify(token)


if __name__ == "__main__":
    test_token = "12345rty"

    verify(test_token)
