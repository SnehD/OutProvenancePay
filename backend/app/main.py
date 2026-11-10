"""FastAPI application factory."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import models  # noqa: F401  (register tables)
from .api import agents, attack_lab, core, payments, purchase, receipts, recovery, transactions
from .config import Settings, load_settings
from .database import Base, make_engine, make_session_factory
from .services.catalogue import seed_catalogue
from .services.crypto import KeyStore
from .services.paypal import PayPalClient
from .services.evidence import EVIDENCE_KEY_NAME
from .services.receipts import RECEIPT_KEY_NAME
from .services.manifest import MANIFEST_KEY_NAME, seed_manifest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("outprovenance")


LIVE_PAYPAL_HOSTS = {"api-m.paypal.com", "api.paypal.com"}


def _refuse_live_paypal(settings: Settings) -> None:
    """This prototype is Sandbox-only: refuse to start if pointed at PayPal's live API."""
    host = (urlparse(settings.paypal_base_url).hostname or "").lower()
    if host in LIVE_PAYPAL_HOSTS:
        raise RuntimeError(
            "PAYPAL_BASE_URL points at PayPal's LIVE API. This prototype is Sandbox-only and will not start "
            "with a live host. Use https://api-m.sandbox.paypal.com.")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    _refuse_live_paypal(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    try:  # one receipt per intent and type, enforced by the database so concurrent requests cannot double-issue
        with engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_receipt_intent_type ON receipts (intent_id, receipt_type)"))
    except Exception:  # an old database that already holds duplicates: keep running, say so
        log.warning("could not create the unique receipt index (existing duplicate receipts?)")
    session_factory = make_session_factory(engine)
    keystore = KeyStore(settings.keys_dir)
    keystore.ensure(MANIFEST_KEY_NAME)
    keystore.ensure(RECEIPT_KEY_NAME)
    keystore.ensure(EVIDENCE_KEY_NAME)
    with session_factory() as session:
        seed_catalogue(session)
        seed_manifest(session, keystore)

    app = FastAPI(
        title="OutProvenance Pay API",
        version="0.1.0",
        description="Hackathon prototype: safer AI-agent purchases. Not a certified security product.",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.keystore = keystore
    app.state.paypal = PayPalClient(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )
    app.include_router(core.router)
    app.include_router(agents.router)
    app.include_router(purchase.router)
    app.include_router(transactions.router)
    app.include_router(payments.router)
    app.include_router(receipts.router)
    app.include_router(recovery.router)
    app.include_router(attack_lab.router)
    log.info("startup complete; paypal_configured=%s ai_configured=%s",
             settings.paypal_configured, settings.ai_configured)
    return app


# Run with: uvicorn app.main:create_app --factory   (no import-time side effects, so tests stay isolated)
