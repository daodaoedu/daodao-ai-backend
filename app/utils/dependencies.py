from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
# from jose import JWTError, jwt

# 假設你有設定這些
SECRET_KEY = "123456789abcdefg"  # 應該從環境變數或配置檔讀取
ALGORITHM = "HS256"

# 用於 OAuth2 token 驗證
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")





# 假設 JWT 的 payload 裡有 sub = user_id
def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="無法驗證使用者",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # user_id: str = payload.get("sub")
        # if user_id is None:
        #     raise credentials_exception
        user_id = 1 # dev

        # 回傳 user info，可以再查 DB 或直接塞 payload 資料
        return {"id": int(user_id)}
    except JWTError:
        raise credentials_exception
