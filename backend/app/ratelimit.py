"""简单的进程内限流：防登录接口暴力破解。

单进程 + 单 worker 部署下足够用（本项目 uvicorn 只起一个 worker）。
每个 IP 在滑动窗口内超过 MAX_ATTEMPTS 次尝试则返回 429。

注意：故意不信任 X-Forwarded-For（前面没有可信反向代理时，
攻击者可伪造该头绕过按 IP 限流），直接使用连接层 IP。
"""
from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request

MAX_ATTEMPTS = 10          # 窗口内最大尝试次数
WINDOW_SECONDS = 60.0      # 滑动窗口（秒）

_attempts: dict[str, list[float]] = {}
_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    if request.client is not None:
        return request.client.host
    return "unknown"


def _prune(now: float) -> None:
    """清理过期记录，防止字典无限增长（调用方已持有锁）。"""
    cutoff = now - WINDOW_SECONDS
    stale = [ip for ip, hits in _attempts.items()
             if not any(t > cutoff for t in hits)]
    for ip in stale:
        del _attempts[ip]


def _count(ip: str, now: float) -> int:
    """窗口内已记录的失败尝试次数（调用方已持有锁）。"""
    return sum(1 for t in _attempts.get(ip, []) if now - t < WINDOW_SECONDS)


def check_login_rate_limit(request: Request) -> None:
    """登录接口的限流检查（依赖项）：超限抛 429，不计入本次。"""
    ip = _client_ip(request)
    with _lock:
        if _count(ip, time.monotonic()) >= MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail=f"登录尝试过于频繁，请 {int(WINDOW_SECONDS)} 秒后再试",
            )


def record_login_attempt(request: Request) -> None:
    """记录一次失败的登录尝试（只在凭证校验失败后调用）。"""
    ip = _client_ip(request)
    now = time.monotonic()
    with _lock:
        hits = [t for t in _attempts.get(ip, []) if now - t < WINDOW_SECONDS]
        hits.append(now)
        _attempts[ip] = hits
        if sum(len(v) for v in _attempts.values()) % 50 == 0:
            _prune(now)


def login_rate_limit(request: Request) -> None:
    """兼容旧依赖：检查 + 记录（新代码请用 check/record 组合）。"""
    check_login_rate_limit(request)
    record_login_attempt(request)
