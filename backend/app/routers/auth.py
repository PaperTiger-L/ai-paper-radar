"""管理员认证：登录签发 JWT、Token 校验、修改密码。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import ratelimit, schemas, security, utils
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenOut)
def login(
    body: schemas.LoginIn,
    request: Request,
    db: Session = Depends(get_db),
    _rl: None = Depends(ratelimit.check_login_rate_limit),
):
    """管理员登录。成功返回 {token, username, expires_in}；失败 401。

    每个 IP 60 秒内失败尝试超过 10 次返回 429（防暴力破解；成功登录不计数）。
    """
    expected_username = utils.get_setting(db, security.ADMIN_USERNAME_KEY)
    stored_hash = utils.get_setting(db, security.ADMIN_HASH_KEY)
    ok = (
        stored_hash is not None
        and body.username == expected_username
        and security.verify_password(body.password, stored_hash)
    )
    if not ok:
        # 只记录用户名，不记录密码
        ratelimit.record_login_attempt(request)
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
    # 用户名变更使旧 token 失效，随后签发携带新版本号的 token
    security.bump_token_version(db)
    utils.log_event(db, "auth", "INFO", f"管理员用户名由 {username} 修改为 {new_username}")
    token, expires_in = security.create_token(db, new_username)
    return {"token": token, "username": new_username, "expires_in": expires_in}


@router.post("/change-password", response_model=schemas.TokenOut)
def change_password(
    body: schemas.ChangePasswordIn,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改管理员密码：校验旧密码，新密码至少 8 位。

    密码变更后所有旧 token 即刻失效；为当前会话签发新 token 并返回，
    前端用新 token 替换本地存储，避免改密后被登出。
    """
    stored_hash = utils.get_setting(db, security.ADMIN_HASH_KEY)
    if not stored_hash or not security.verify_password(body.old_password, stored_hash):
        utils.log_event(db, "auth", "WARNING", f"修改密码失败：旧密码不正确（{username}）")
        raise HTTPException(status_code=400, detail="旧密码不正确")
    utils.set_setting(db, security.ADMIN_HASH_KEY, security.hash_password(body.new_password))
    security.bump_token_version(db)
    utils.log_event(db, "auth", "INFO", f"管理员 {username} 修改密码成功，旧 token 已失效")
    token, expires_in = security.create_token(db, username)
    return {"token": token, "username": username, "expires_in": expires_in}
