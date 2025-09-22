import os

import jwt  # pyjwt 的標準 import 名稱
from fastapi import Depends
from jwt import ExpiredSignatureError, InvalidTokenError
from logger import AppLogger

logger = AppLogger(__name__).get_logger()

JWT_SECURITY = os.getenv("JWT_SECURITY")
JWT_EXPIRATION = os.getenv("JWT_EXPIRATION")



def verify(token: str):
    try:
        payload = jwt.decode(token, JWT_SECURITY, algorithms=["HS256"])
        logger.info(f"驗證成功，payload:{payload}")
        return payload
    except ExpiredSignatureError:
        logger.info("Token 已過期")
    except InvalidTokenError:
        logger.info("無效的 Token")

    # {'id': 20, '_id': '2e', 'time': , 'isTemp': False, 'iat': 1756544897, 'exp': 1756566497}





if __name__ == "__main__":
    test_token = os.getenv("MY_TOKEN_ID", "test")
    
    logger.info(f"Testing token: {test_token}")


    verify(test_token)
