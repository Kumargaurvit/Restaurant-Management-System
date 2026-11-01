import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from restaurant_management_system.auth.router import router as auth_router
from restaurant_management_system.billing.router import router as billing_router
from restaurant_management_system.booking.router import router as booking_router
from restaurant_management_system.chatbot.offers_router import router as offers_router
from restaurant_management_system.chatbot.router import router as chat_router
from restaurant_management_system.config import get_settings
from restaurant_management_system.customers.router import reports_router
from restaurant_management_system.customers.router import router as customers_router
from restaurant_management_system.db.session import get_engine
from restaurant_management_system.logging_config import configure_logging
from restaurant_management_system.messaging.router import router as messaging_router
from restaurant_management_system.restaurant.router import router as restaurant_router
from restaurant_management_system.retention.router import router as retention_router
from restaurant_management_system.scheduler import build_scheduler


request_logger = logging.getLogger("app.requests")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = build_scheduler() if get_settings().scheduler_enabled else None
    if scheduler:
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        # Only the path is logged: query strings can hold a guest's phone number.
        request_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            request_logger.exception(
                "%s %s failed",
                request.method,
                request.url.path,
                extra={"request_id": request_id, "method": request.method, "path": request.url.path},
            )
            raise
        request_logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(billing_router)
    app.include_router(customers_router)
    app.include_router(reports_router)
    app.include_router(booking_router)
    app.include_router(retention_router)
    app.include_router(messaging_router)
    app.include_router(restaurant_router)
    app.include_router(offers_router)
    app.include_router(chat_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
