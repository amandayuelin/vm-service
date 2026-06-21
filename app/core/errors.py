from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def request_id_from_request(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or request.headers.get("X-Request-ID") or "")


def error_body(code: str, message: str, request_id: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details or {},
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        request_id = request_id_from_request(request)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, request_id, exc.details),
            headers={"X-Request-ID": request_id} if request_id else None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = request_id_from_request(request)
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_error",
                "Request validation failed.",
                request_id,
                {"errors": jsonable_encoder(exc.errors())},
            ),
            headers={"X-Request-ID": request_id} if request_id else None,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = request_id_from_request(request)
        logger.exception("unexpected_error", extra={"request_id": request_id})
        return JSONResponse(
            status_code=500,
            content=error_body("internal_server_error", "Internal server error.", request_id),
            headers={"X-Request-ID": request_id} if request_id else None,
        )
