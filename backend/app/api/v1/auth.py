"""认证接口：登录签发 JWT。"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.response import ok
from app.application.errors import ApplicationError
from app.core.security import authenticate, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest) -> dict:
    """用户名密码登录，返回 JWT。

    Raises:
        ApplicationError: 40001 用户名或密码错误。
    """
    user = authenticate(body.username, body.password)
    if user is None:
        raise ApplicationError(40001, "用户名或密码错误")
    token = create_access_token(user["userId"], user["username"], user["roles"])
    return ok({"token": token, "userId": user["userId"], "roles": user["roles"]})
