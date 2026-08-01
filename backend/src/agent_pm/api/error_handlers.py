"""The single place application errors become HTTP responses.

Services raise domain errors; nothing below the API layer imports FastAPI.
That keeps services callable from the scheduler, which has no HTTP context.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent_pm.core.errors import AgentPMError
from agent_pm.core.logging import get_logger

logger = get_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AgentPMError)
    async def _domain_error(request: Request, exc: AgentPMError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "request_failed",
                extra={"path": request.url.path, "code": exc.code},
                exc_info=exc,
            )
        else:
            logger.info(
                "request_rejected",
                extra={"path": request.url.path, "code": exc.code},
            )
        headers = (
            {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        )
        return JSONResponse(
            status_code=exc.status_code, content=exc.to_payload(), headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "validation_error",
                "message": "Request body or parameters are invalid",
                "details": {"errors": exc.errors()},
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Nothing internal leaks to the client; the detail goes to the log.
        logger.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "internal_error",
                "message": "Something went wrong. The incident has been logged.",
                "details": {},
            },
        )
