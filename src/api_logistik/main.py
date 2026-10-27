from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from api_logistik.api.router import router
from api_logistik.config import Settings, load_settings
from api_logistik.db.api_key_repository import ApiKeyRepository
from api_logistik.db.karyawan_repository import KaryawanRepository
from api_logistik.db.pool import PoolManager
from api_logistik.errors import ApplicationError
from api_logistik.logging_config import configure_logging
from api_logistik.middleware.request_context import RequestContextMiddleware
from api_logistik.schemas.responses import envelope


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    selected = settings or load_settings()
    pool = PoolManager(selected)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(
        title="API_LOGISTIK",
        version="0.1.0.dev0",
        lifespan=lifespan,
        docs_url="/docs" if selected.expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if selected.expose_docs else None,
    )
    app.state.settings = selected
    app.state.pool = pool
    app.state.auth_repository_factory = ApiKeyRepository
    app.state.karyawan_repository_factory = KaryawanRepository
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        request.state.error_category = exc.code
        return JSONResponse(envelope(False, exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request.state.error_category = "request_validation"
        return JSONResponse(
            envelope(False, "REQUEST_422", "Input request tidak valid"), status_code=422
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            envelope(False, f"HTTP_{exc.status_code}", "Request tidak dapat diproses"),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    app.include_router(router)
    return app


def run() -> None:
    configure_logging()
    settings = load_settings()
    uvicorn.run(
        "api_logistik.main:create_app",
        factory=True,
        host=settings.bind_host,
        port=settings.port,
        access_log=False,
        log_config=None,
        proxy_headers=False,
    )
