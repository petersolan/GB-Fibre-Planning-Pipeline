"""FastAPI application: fibre planning data, read-only.

Run locally:  uvicorn fibre_planning.api.app:app --port 8000
Docs:         http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from fibre_planning import __version__

from .db import get_engine
from .observability import RequestContextMiddleware, SecurityHeadersMiddleware, configure_logging, log
from .routes import router
from .schemas import Health, Ready


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Fibre planning API",
        version=__version__,
        description="Premises, people and road links for gigabit broadband planning (read-only).",
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(router)

    @app.get("/health", response_model=Health, tags=["ops"])
    def health() -> Health:
        """Liveness: the process is up (no dependencies checked)."""
        return Health(status="ok")

    @app.get("/ready", response_model=Ready, tags=["ops"])
    def ready() -> Ready:
        """Readiness: the database answers and holds a pipeline run."""
        try:
            with get_engine().connect() as conn:
                last = conn.execute(text("SELECT max(run_at) FROM fibre.pipeline_run")).scalar()
        except SQLAlchemyError as exc:
            log.warning("database not ready", error=type(exc).__name__)
            raise HTTPException(503, "Database unavailable") from None
        return Ready(status="ready", database="ok", last_run_at=last)

    @app.get("/metrics", response_class=PlainTextResponse, tags=["ops"], include_in_schema=False)
    def metrics() -> PlainTextResponse:
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
