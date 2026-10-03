"""认证与用户（T4.1）。

MVP 用户体系：内置静态账号（开发/测试用），生产替换为组织架构 SSO/LDAP 适配器。
JWT 签发与校验使用 PyJWT（HS256）。
"""

import jwt

from app.core.config import get_settings

# 内置账号：id 与流程 DSL 中的审批人 ID 对应（如 fixed_list user_ids）
DEFAULT_USERS: dict[str, dict] = {
    "admin": {"id": "admin-1", "password": "admin123", "roles": ["admin"]},
    "alice": {"id": "user-of-approve_1", "password": "alice123", "roles": ["approver"]},
    "bob": {"id": "boss-1", "password": "bob123", "roles": ["initiator", "approver"]},
}

# JWT 错误码（40001 认证失败 / 40003 权限不足）


def authenticate(username: str, password: str) -> dict | None:
    """校验用户名密码，成功返回用户信息，失败返回 None。"""
    user = DEFAULT_USERS.get(username)
    if user and user["password"] == password:  # 生产环境必须替换为哈希比对
        return {"userId": user["id"], "username": username, "roles": user["roles"]}
    return None


def create_access_token(user_id: str, username: str, roles: list[str]) -> str:
    """签发 JWT（HS256，含过期时间）。"""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "username": username,
        "roles": roles,
        "exp": _expiry(settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """解码并校验 JWT，失败抛 jwt.PyJWTError。"""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def _expiry(minutes: int):
    """计算过期时间戳。"""
    from datetime import datetime, timedelta, timezone

    return int((datetime.now(timezone.utc) + timedelta(minutes=minutes)).timestamp())
