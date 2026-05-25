from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import create_router
from app.api import support
from app.container import Container
from app.core.config import settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    container = Container()
    app.state.container = container
    app.include_router(create_router(container))
    app.include_router(support.router)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "llm_model": settings.llm_model,
            "small_llm_model": settings.small_llm_model,
            "es_index": settings.es_index,
            "rerank_provider": settings.rerank_provider,
            "rerank_model": settings.rerank_model_name,
            "fusion_top_k": settings.fusion_top_k,
            "rerank_top_n": settings.rerank_top_n,
        }

    @app.on_event("shutdown")
    async def shutdown():
        await container.close()

    return app


app = create_app()
