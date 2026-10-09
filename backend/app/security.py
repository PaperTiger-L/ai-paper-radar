"""安全模块：管理员密码哈希（PBKDF2）与 JWT 签发/校验。

密码存储格式：`<salt_hex>$<hash_hex>`，pbkdf2_hmac(sha256, 20 万次迭代)。
JWT 使用 HS256，密钥优先级：JWT_SECRET 环境变量 > Setting 表（auth.jwt_secret，
缺省则首次启动随机生成并持久化）。
token 载荷携带版本号 ver：修改密码/用户名时版本号 +1，旧 token 即刻失效。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

import jwt

from . import utils
from .config import settings

ADMIN_HASH_KEY = "auth.admin_hash"
ADMIN_USERNAME_KEY = "auth.admin_username"
JWT_SECRET_KEY = "auth.jwt_secret"
TOKEN_VERSION_KEY = "auth.token_version"

_PBKDF2_ITERATIONS = 200_000


# ---------------------------------------------------------------------------
# 密码哈希
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """对明文密码做 PBKDF2 哈希，返回可存储的字符串。"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验明文密码与存储哈希是否一致（常量时间比较）。"""
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERATIONS
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def get_jwt_secret(db) -> str:
    """获取 JWT 密钥。

    优先级：JWT_SECRET 环境变量 > Setting 表持久化的随机密钥。
    注意：设置/修改环境变量会使之前签发的所有 token 失效。
    """
    if settings.jwt_secret:
        return settings.jwt_secret
    secret = utils.get_setting(db, JWT_SECRET_KEY)
    if not secret:
        secret = secrets.token_urlsafe(48)
        utils.set_setting(db, JWT_SECRET_KEY, secret)
    return secret


def get_token_version(db) -> int:
    """当前 token 版本号（缺省 0，保证升级前签发的旧 token 继续有效）。"""
    try:
        return int(utils.get_setting(db, TOKEN_VERSION_KEY, "0") or "0")
    except (ValueError, TypeError):
        return 0


def bump_token_version(db) -> int:
    """版本号 +1 并持久化，返回新版本号。修改密码/用户名后调用。"""
    new_ver = get_token_version(db) + 1
    utils.set_setting(db, TOKEN_VERSION_KEY, str(new_ver))
    return new_ver


def create_token(db, username: str, remember: bool = False) -> tuple[str, int]:
    """签发登录 token。默认 8 小时有效，remember=True 时 30 天。

    返回 (token, expires_in_seconds)。"""
    expires_in = 30 * 24 * 3600 if remember else 8 * 3600
    now_ts = int(time.time())
    payload = {
        "sub": username,
        "ver": get_token_version(db),
        "iat": now_ts,
        "exp": now_ts + expires_in,
    }
    token = jwt.encode(payload, get_jwt_secret(db), algorithm="HS256")
    return token, expires_in


def decode_token(db, token: str) -> str | None:
    """校验 token，成功返回用户名，失败返回 None。

    除签名与过期时间外，还校验版本号：改密/改用户名后旧 token 即刻失效。
    """
    try:
        payload = jwt.decode(token, get_jwt_secret(db), algorithms=["HS256"])
        sub = payload.get("sub")
        if not (isinstance(sub, str) and sub):
            return None
        # 兼容升级前签发的 token（无 ver 视为 0）
        if int(payload.get("ver", 0)) != get_token_version(db):
            return None
        return sub
    except Exception:
        return None
