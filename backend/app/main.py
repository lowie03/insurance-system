"""The FastAPI application.

Run from the project root:
    uvicorn backend.app.main:create_app --factory --reload
Interactive API docs: http://localhost:8000/docs
"""
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db.session import Base, make_session_factory
from backend.app.routes import broker, payments, policies, quotes, verify
from backend.app.services.paystack import PaystackClient
from backend.app.settings import Settings
from insurance_core import config
from insurance_core.model_io import load_bundle


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory: tests pass their own settings (temporary database, test key)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Runs ONCE at startup: load the model and connect to the database
        app.state.settings = settings
        app.state.bundle = load_bundle(settings.model_path)
        engine, app.state.session_factory = make_session_factory(settings.database_url)
        Base.metadata.create_all(engine)        # dev convenience; Alembic migrations replace this later
        settings.pdf_storage_dir.mkdir(parents=True, exist_ok=True)
        paystack = (PaystackClient(settings.paystack_secret_key, settings.paystack_base_url)
                    if settings.payment_mode == "paystack" else None)
        app.state.paystack = paystack
        yield
        engine.dispose()
        if paystack is not None:
            paystack.close()                    # close the client WE created (tests may swap in a fake)

    app = FastAPI(title="Insurance Recommendation & Issuance API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.frontend_origins,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Process-Time"])

    @app.middleware("http")
    async def time_requests(request: Request, call_next):
        """Every response says how long the server took: evidence for Objective 2."""
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.4f}"
        return response

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "model_version": app.state.bundle["model_version"],
                "payment_mode": settings.payment_mode, "config_versions": config.versions()}

    app.include_router(quotes.router)
    app.include_router(policies.router)
    if settings.payment_mode == "simulated":
        app.include_router(policies.simulated_router)
    app.include_router(verify.router)
    app.include_router(payments.router)
    app.include_router(broker.router)
    return app