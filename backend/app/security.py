"""安全模块：管理员密码哈希（PBKDF2）与 JWT 签发/校验。

密码存储格式：`<salt_hex>$<hash_hex>`，pbkdf2_hmac(sha256, 20 万次迭代)。
JWT 使用 HS256，密钥存于 Setting 表（auth.jwt_secret），缺省则首次启动随机生成。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

import jwt

from . import utils

ADMIN_HASH_KEY = "auth.admin_hash"
ADMIN_USERNAME_KEY = "auth.admin_username"
JWT_SECRET_KEY = "auth.jwt_secret"

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
    """获取 JWT 密钥；不存在则随机生成并持久化到 Setting 表。"""
    secret = utils.get_setting(db, JWT_SECRET_KEY)
    if not secret:
        secret = secrets.token_urlsafe(48)
        utils.set_setting(db, JWT_SECRET_KEY, secret)
    return secret


def create_token(db, username: str, remember: bool = False) -> tuple[str, int]:
    """签发登录 token。默认 8 小时有效，remember=True 时 30 天。

    返回 (token, expires_in_seconds)。"""
    expires_in = 30 * 24 * 3600 if remember else 8 * 3600
    now_ts = int(time.time())
    payload = {"sub": username, "iat": now_ts, "exp": now_ts + expires_in}
    token = jwt.encode(payload, get_jwt_secret(db), algorithm="HS256")
    return token, expires_in


def decode_token(db, token: str) -> str | None:
    """校验 token，成功返回用户名，失败返回 None。"""
    try:
        payload = jwt.decode(token, get_jwt_secret(db), algorithms=["HS256"])
        sub = payload.get("sub")
        return sub if isinstance(sub, str) and sub else None
    except Exception:
        return None
