from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from app.core.errors import (
    UPSTREAM_CONNECTION_ERROR,
    UPSTREAM_ERROR,
    UPSTREAM_RATE_LIMITED,
    UPSTREAM_TIMEOUT,
    map_upstream_error,
)


def _instance(cls):
    """构造 openai 异常实例，绕过其 __init__ 的繁琐参数。"""
    return cls.__new__(cls)


def test_timeout_maps_to_timeout_504():
    code, status = map_upstream_error(_instance(APITimeoutError))
    assert code == UPSTREAM_TIMEOUT
    assert status == 504


def test_builtin_timeout_also_maps_to_504():
    code, status = map_upstream_error(TimeoutError("timeout"))
    assert code == UPSTREAM_TIMEOUT
    assert status == 504


def test_rate_limit_maps_to_rate_limited_429():
    code, status = map_upstream_error(_instance(RateLimitError))
    assert code == UPSTREAM_RATE_LIMITED
    assert status == 429


def test_connection_error_maps_to_connection_error_502():
    code, status = map_upstream_error(_instance(APIConnectionError))
    assert code == UPSTREAM_CONNECTION_ERROR
    assert status == 502


def test_builtin_connection_error_maps_to_502():
    code, status = map_upstream_error(ConnectionError("connection refused"))
    assert code == UPSTREAM_CONNECTION_ERROR
    assert status == 502


def test_unknown_error_falls_back_to_upstream_error_502():
    code, status = map_upstream_error(RuntimeError("boom"))
    assert code == UPSTREAM_ERROR
    assert status == 502


def test_auth_error_maps_to_auth_error_502():
    code, status = map_upstream_error(_instance(AuthenticationError))
    assert code == "upstream_auth_error"
    assert status == 502