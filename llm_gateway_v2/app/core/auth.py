import os

from fastapi import Depends, Header

from app.core.errors import UNAUTHORIZED, GatewayError


async def verify_token(
    authorization: str | None = Header(default=None),
) -> None:
    expected_token = os.getenv("GATEWAY_API_KEY", "test-key")
    if not authorization or not authorization.startswith("Bearer "):
        raise GatewayError(UNAUTHORIZED, "Unauthorized", status_code=401)

    token = authorization.removeprefix("Bearer ")
    if token != expected_token:
        raise GatewayError(UNAUTHORIZED, "Unauthorized", status_code=401)


verify_token_dependency = Depends(verify_token)
