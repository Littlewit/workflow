"""开放接口（M5-T5.4）：第三方系统通过 appKey + HMAC 签名调用。

协议（详细设计 §5.1）：
- 头部：X-App-Key / X-Timestamp（毫秒，偏差≤300s）/ X-Nonce（10min 去重）/ X-Sign
- 签名：HMAC-SHA256(appSecret, method + "\n" + path + "\n" + timestamp + "\n" + nonce + "\n" + sha256(body))

应用注册表 MVP 为内置字典；生产替换为数据库表 + 管理端签发。
"""

import hashlib
import hmac
import time

from fastapi import Request

from app.application.errors import ApplicationError

# 应用注册表（MVP 静态配置；生产迁移到 sys_open_app 表）
OPEN_APPS: dict[str, str] = {
    "demo-app": "demo-secret-0123456789abcdef",
}

# Nonce 去重窗口（10 分钟，与时间戳窗口一致）
_NONCE_TTL_SECONDS = 600
_seen_nonces: dict[str, float] = {}


def _purge_nonces(now: float) -> None:
    """清理过期 nonce（防止内存无限增长）。"""
    expired = [k for k, t in _seen_nonces.items() if now - t > _NONCE_TTL_SECONDS]
    for k in expired:
        _seen_nonces.pop(k, None)


def compute_signature(app_secret: str, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    """计算请求签名（开放给第三方 SDK 复用）。"""
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
    return hmac.new(app_secret.encode(), message.encode(), hashlib.sha256).hexdigest()


async def verify_open_request(request: Request) -> str:
    """校验开放接口请求：签名 / 时间戳窗口 / Nonce 防重放。

    Returns:
        appKey（用于业务侧鉴权）。

    Raises:
        ApplicationError: 40005 签名/时间戳/Nonce 校验失败。
    """
    app_key = request.headers.get("X-App-Key", "")
    timestamp = request.headers.get("X-Timestamp", "")
    nonce = request.headers.get("X-Nonce", "")
    sign = request.headers.get("X-Sign", "")
    app_secret = OPEN_APPS.get(app_key)
    if not app_secret:
        raise ApplicationError(40005, "未知的 appKey")

    now_ms = time.time() * 1000
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise ApplicationError(40005, "时间戳格式非法") from exc
    if abs(now_ms - ts) > 300_000:
        raise ApplicationError(40005, "时间戳偏差超过 300 秒（防重放）")

    now_s = time.time()
    _purge_nonces(now_s)
    if nonce in _seen_nonces:
        raise ApplicationError(40005, "Nonce 已被使用（防重放）")

    body = await request.body()
    expected = compute_signature(app_secret, request.method, request.url.path, timestamp, nonce, body)
    if not hmac.compare_digest(expected, sign):
        raise ApplicationError(40005, "签名校验失败")

    _seen_nonces[nonce] = now_s  # 校验通过后才记录，避免攻击者用假签名污染去重表
    return app_key
