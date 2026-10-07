"""Structured logging, request IDs and Prometheus metrics for the API."""

import logging
import time
import uuid

import structlog
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUESTS = Counter("api_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("api_request_seconds", "HTTP request latency", ["method", "route"])


def configure_logging(level: int = logging.INFO) -> None:
    """JSON logs, one line per event, ready for a log collector."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


log = structlog.get_logger("fibre_planning.api")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Tag each request with an ID, time it, log it and count it.

    Metrics use the route template (/v1/postcodes/{postcode}), not the raw
    path, so label cardinality stays bounded and no postcodes end up in metrics.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            elapsed = time.perf_counter() - start
            route = request.scope.get("route")
            template = getattr(route, "path", "unmatched")
            REQUESTS.labels(request.method, template, str(status)).inc()
            LATENCY.labels(request.method, template).observe(elapsed)
            log.info(
                "request", method=request.method, route=template, status=status, ms=round(elapsed * 1000, 1)
            )
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response
