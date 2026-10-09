"""FastAPI 依赖：数据库会话、Bearer Token 鉴权。"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import security
from .database import SessionLocal

_bearer = HTTPBearer(auto_error=False)


def get_db():
    """请求级数据库会话依赖。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> str:
    """校验 Authorization: Bearer <token>，返回管理员用户名。

    token 缺失或无效时抛出 401。除登录接口外所有 /api 接口均依赖此函数。
    """
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    username = security.decode_token(db, creds.credentials)
    if not username:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return username
