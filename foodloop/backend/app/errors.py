"""One error shape for the whole API, so the React app can show friendly messages.

Business errors:   {"detail": "Only 2 portions left."}
Validation errors: {"detail": "Please check the highlighted fields.",
                    "errors": [{"field": "price_paise", "message": "..."}]}
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Raised by services when a business rule says no.

    `field` points the UI at one form input; `errors` lists several {"field", "message"} problems at once.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        field: str | None = None,
        errors: list[dict[str, str]] | None = None,
    ):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.errors = errors or ([{"field": field, "message": detail}] if field else [])


def _field_name(loc: tuple) -> str:
    parts = [str(part) for part in loc if part not in ("body", "query", "path")]
    return ".".join(parts) or "request"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        body: dict = {"detail": exc.detail}
        if exc.errors:
            body["errors"] = exc.errors
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for error in exc.errors():
            message = error.get("msg", "Invalid value")
            # Pydantic prefixes custom messages with "Value error, "; users don't need that.
            message = message.removeprefix("Value error, ")
            errors.append({"field": _field_name(tuple(error.get("loc", ()))), "message": message})
        return JSONResponse(
            status_code=422,
            content={"detail": "Please check the highlighted fields.", "errors": errors},
        )
