from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        code: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.details: dict[str, Any] = details if details is not None else {}
        super().__init__(code)


def error_response(
    code: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "details": details if details is not None else {},
            }
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.code, exc.status_code, exc.details)


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = [
        {
            "loc": [str(part) for part in err.get("loc", ())],
            "type": str(err.get("type", "")),
        }
        for err in exc.errors()
    ]
    return error_response(
        code="validation_error",
        status_code=422,
        details={"errors": errors},
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    return error_response(
        code="internal_error",
        status_code=500,
        details={},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        validation_error_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
