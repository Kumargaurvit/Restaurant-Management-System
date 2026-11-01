from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from restaurant_management_system.auth.router import router as auth_router
from restaurant_management_system.billing.router import router as billing_router
from restaurant_management_system.chatbot.offers_router import router as offers_router
from restaurant_management_system.chatbot.router import router as chat_router
from restaurant_management_system.config import get_settings
from restaurant_management_system.customers.router import reports_router
from restaurant_management_system.customers.router import router as customers_router
from restaurant_management_system.db.session import get_engine
from restaurant_management_system.restaurant.router import router as restaurant_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
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
    app.include_router(restaurant_router)
    app.include_router(offers_router)
    app.include_router(chat_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
