"""
app/core/responses.py

Centralised API response helpers and global exception handlers.
Every endpoint returns the same envelope:

    {
        "status":  <int>,
        "success": <bool>,
        "message": <str>,
        "data":    <T | null>
    }
"""
from typing import Any, Generic, Optional, TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

DataT = TypeVar("DataT")


# ---------------------------------------------------------------------------
# Generic envelope schema — use as response_model=ApiResponse[YourModel]
# ---------------------------------------------------------------------------

class ApiResponse(BaseModel, Generic[DataT]):
    status: int
    success: bool
    message: str
    data: Optional[DataT] = None


# ---------------------------------------------------------------------------
# Helper for route handlers
# ---------------------------------------------------------------------------

def success_response(
    message: str,
    status_code: int = 200,
    data: Any = None,
) -> dict:
    """Build a success envelope dict that FastAPI will serialise."""
    return {
        "status": status_code,
        "success": True,
        "message": message,
        "data": data,
    }


# ---------------------------------------------------------------------------
# Global exception handlers — register once in main.py
# ---------------------------------------------------------------------------

def _extract_message(detail: object, fallback: str = "An error occurred") -> str:
    """Pull a human-readable message out of an HTTPException detail."""
    if isinstance(detail, str) and detail.strip():
        return detail
    if isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, dict) and first.get("msg"):
            return str(first["msg"])
    if isinstance(detail, dict) and detail.get("msg"):
        return str(detail["msg"])
    return fallback


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global handlers so every error follows the envelope format."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": exc.status_code,
                "success": False,
                "message": _extract_message(exc.detail),
                "data": None,
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ):
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "success": False,
                "message": _extract_message(exc.errors(), fallback="Validation error"),
                "data": jsonable_encoder(exc.errors()),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(_request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "status": 500,
                "success": False,
                "message": "Internal server error",
                "data": None,
            },
        )
