from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, chat, knowledge, memory, portfolio, research
from app.core.config import get_settings
from app.core.database import create_schema_for_development


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.app_env == "test":
        await create_schema_for_development()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(chat.router, prefix=settings.api_v1_prefix)
    app.include_router(research.router, prefix=settings.api_v1_prefix)
    app.include_router(portfolio.router, prefix=settings.api_v1_prefix)
    app.include_router(memory.router, prefix=settings.api_v1_prefix)
    app.include_router(knowledge.router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
