"""管理员认证：登录签发 JWT、Token 校验、修改密码。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, security, utils
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    """管理员登录。成功返回 {token, username, expires_in}；失败 401。"""
    expected_username = utils.get_setting(db, security.ADMIN_USERNAME_KEY)
    stored_hash = utils.get_setting(db, security.ADMIN_HASH_KEY)
    ok = (
        stored_hash is not None
        and body.username == expected_username
        and security.verify_password(body.password, stored_hash)
    )
    if not ok:
        # 只记录用户名，不记录密码
        utils.log_event(db, "auth", "WARNING", f"登录失败：用户名 {body.username}")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, expires_in = security.create_token(db, body.username, remember=body.remember)
    utils.log_event(db, "auth", "INFO", f"管理员 {body.username} 登录成功")
    return {"token": token, "username": body.username, "expires_in": expires_in}


@router.get("/me", response_model=schemas.MeOut)
def me(username: str = Depends(get_current_user)):
    """返回当前登录的管理员用户名（供前端校验 Token 有效性）。"""
    return {"username": username}


@router.post("/change-username", response_model=schemas.TokenOut)
def change_username(
    body: schemas.ChangeUsernameIn,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改管理员用户名：需校验当前密码。成功后签发新 token（sub 为新用户名）。"""
    stored_hash = utils.get_setting(db, security.ADMIN_HASH_KEY)
    if not stored_hash or not security.verify_password(body.current_password, stored_hash):
        utils.log_event(db, "auth", "WARNING", f"修改用户名失败：密码不正确（{username}）")
        raise HTTPException(status_code=400, detail="当前密码不正确")
    new_username = body.new_username.strip()
    utils.set_setting(db, security.ADMIN_USERNAME_KEY, new_username)
    utils.log_event(db, "auth", "INFO", f"管理员用户名由 {username} 修改为 {new_username}")
    token, expires_in = security.create_token(db, new_username)
    return {"token": token, "username": new_username, "expires_in": expires_in}


@router.post("/change-password", response_model=schemas.OkOut)
def change_password(
    body: schemas.ChangePasswordIn,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改管理员密码：校验旧密码，新密码至少 8 位。"""
    stored_hash = utils.get_setting(db, security.ADMIN_HASH_KEY)
    if not stored_hash or not security.verify_password(body.old_password, stored_hash):
        utils.log_event(db, "auth", "WARNING", f"修改密码失败：旧密码不正确（{username}）")
        raise HTTPException(status_code=400, detail="旧密码不正确")
    utils.set_setting(db, security.ADMIN_HASH_KEY, security.hash_password(body.new_password))
    utils.log_event(db, "auth", "INFO", f"管理员 {username} 修改密码成功")
    return {"ok": True}
