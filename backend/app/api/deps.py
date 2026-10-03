"""API 依赖：当前用户提取与 RBAC 校验。"""

from dataclasses import dataclass, field

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.errors import ApplicationError
from app.core.security import decode_token

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """当前请求用户（由 JWT 解析）。"""

    user_id: str
    username: str
    roles: list[str] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        """是否管理员。"""
        return "admin" in self.roles


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """从 Authorization: Bearer <jwt> 解析当前用户。

    Raises:
        ApplicationError: 40001 未认证或 token 无效。
    """
    if credentials is None:
        raise ApplicationError(40001, "未认证：缺少 Bearer token")
    try:
        payload = decode_token(credentials.credentials)
    except Exception as exc:
        raise ApplicationError(40001, f"无效的认证凭据: {exc}") from exc
    return CurrentUser(
        user_id=payload["sub"], username=payload.get("username", ""), roles=payload.get("roles", [])
    )


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """管理员守卫。

    Raises:
        ApplicationError: 40003 权限不足。
    """
    if not user.is_admin:
        raise ApplicationError(40003, "需要管理员权限")
    return user
