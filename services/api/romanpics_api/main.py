from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text

from . import __version__
from .api import router
from .config import Settings, get_settings
from .database import build_engine, build_session_factory
from .services.votes import InMemorySlidingWindowLimiter


def create_app(settings: Settings | None = None, *, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or build_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    application = FastAPI(
        title="RomanPics API",
        version=__version__,
        description=(
            "Consumer discovery API over authoritative Roman-related sources. "
            "Original science products remain upstream."
        ),
        license_info={"name": "MIT"},
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = build_session_factory(engine)
    application.state.vote_limiter = InMemorySlidingWindowLimiter(
        settings.rate_limit_votes_per_minute
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "If-None-Match"],
        expose_headers=["ETag"],
        max_age=600,
    )

    @application.middleware("http")
    async def browser_and_security_headers(request: Request, call_next):
        if request.method in {"PUT", "DELETE", "POST", "PATCH"} and request.url.path.startswith(
            "/v1/me/votes/"
        ):
            origin = request.headers.get("origin")
            if not origin or origin not in settings.allowed_origins:
                return _problem(
                    request,
                    status=403,
                    title="Forbidden",
                    detail="The request Origin is missing or is not allowed.",
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )
        return response

    @application.exception_handler(HTTPException)
    async def http_problem(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return _problem(
            request, status=exc.status_code, title=_title(exc.status_code), detail=detail
        )

    @application.exception_handler(RequestValidationError)
    async def validation_problem(request: Request, exc: RequestValidationError):
        return _problem(
            request,
            status=422,
            title="Unprocessable Content",
            detail="Request parameters did not pass validation.",
            errors=exc.errors(),
        )

    @application.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/readyz", include_in_schema=False)
    def readyz() -> dict[str, str]:
        try:
            with engine.connect() as connection:
                connection.execute(text("select 1"))
        except Exception as exc:
            raise HTTPException(503, "database is unavailable") from exc
        return {"status": "ready"}

    application.include_router(router)
    return application


def _problem(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    errors: list[dict[str, object]] | None = None,
) -> JSONResponse:
    body: dict[str, object] = {
        "type": f"https://romanpics.org/problems/http-{status}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def _title(status: int) -> str:
    return {
        400: "Bad Request",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        429: "Too Many Requests",
        503: "Service Unavailable",
    }.get(status, "Request Failed")


app = create_app()
