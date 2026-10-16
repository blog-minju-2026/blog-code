"""오류 응답 형식 (API 명세서 2.4).

모든 오류는 {"error": {"code", "message", "fields"?, "detail"?}} 모양으로 돌려준다.
"""

import math

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class APIError(exceptions.APIException):
    """명세서의 오류 코드를 그대로 던질 때 쓴다. 예: raise APIError(409, "CONFLICT", "이미 지은 한채가 있어요.")"""

    def __init__(self, status_code, code, message, fields=None, detail=None):
        self.status_code = status_code
        self.error_code = code
        self.message = message
        self.fields = fields
        self.extra = detail
        super().__init__(message)


DEFAULT_MESSAGES = {
    "VALIDATION_ERROR": "입력한 내용을 확인해 주세요.",
    "AUTH_REQUIRED": "로그인이 필요해요.",
    "FORBIDDEN": "들어갈 수 없는 곳이에요.",
    "NOT_FOUND": "찾을 수 없어요.",
    "SERVER_ERROR": "잠시 후 다시 시도해 주세요.",
}


def _body(code, message=None, fields=None, detail=None):
    error = {"code": code, "message": message or DEFAULT_MESSAGES.get(code, "")}
    if fields:
        error["fields"] = fields
    if detail:
        error["detail"] = detail
    return {"error": error}


def _flatten(errors):
    """DRF 검증 오류 {"title": ["..."]} 를 칸별 한 문장 {"title": "..."} 으로 줄인다."""
    if isinstance(errors, dict):
        flat = {}
        for key, value in errors.items():
            if isinstance(value, (list, tuple)) and value:
                first = value[0]
                flat[key] = _flatten(first) if isinstance(first, dict) else str(first)
            elif isinstance(value, dict):
                flat[key] = _flatten(value)
            else:
                flat[key] = str(value)
        return flat
    if isinstance(errors, (list, tuple)):
        return {"non_field_errors": str(errors[0])} if errors else {}
    return {"non_field_errors": str(errors)}


def exception_handler(exc, context):
    if isinstance(exc, APIError):
        return Response(_body(exc.error_code, exc.message, exc.fields, exc.extra), status=exc.status_code)
    if isinstance(exc, exceptions.ValidationError):
        return Response(_body("VALIDATION_ERROR", fields=_flatten(exc.detail)), status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        return Response(_body("AUTH_REQUIRED"), status=status.HTTP_401_UNAUTHORIZED)
    if isinstance(exc, (exceptions.PermissionDenied, DjangoPermissionDenied)):
        message = str(exc.detail) if isinstance(exc, exceptions.PermissionDenied) and exc.detail else None
        if message and "CSRF" in message:
            message = "보안 확인에 실패했어요. 새로고침한 뒤 다시 시도해 주세요."
        elif message == exceptions.PermissionDenied.default_detail:
            message = None
        return Response(_body("FORBIDDEN", message), status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, (exceptions.NotFound, Http404)):
        return Response(_body("NOT_FOUND"), status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, exceptions.Throttled):
        seconds = max(1, math.ceil(exc.wait or 1))
        after = f"{seconds}초" if seconds < 60 else f"{math.ceil(seconds / 60)}분"
        return Response(
            _body("TOO_MANY_REQUESTS", f"요청이 너무 잦아요. {after} 뒤에 다시 시도해 주세요.", detail={"retry_after": seconds}),
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(seconds)},
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        code = "METHOD_NOT_ALLOWED" if response.status_code == 405 else "BAD_REQUEST"
        response.data = _body(code, str(getattr(exc, "detail", "")) or None)
    return response
