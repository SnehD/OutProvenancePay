"""Application settings, read from environment variables (and an optional backend/.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Policy constants live here so the engine and the docs agree on one source of truth.
POLICY_VERSION = "policy-2026.1"
APPROVAL_THRESHOLD_USD = "75.00"  # strictly above this => REQUIRE_APPROVAL
MAX_PURCHASE_USD = "100.00"  # strictly above this => DENY
SUPPORTED_CURRENCIES = ("USD",)
MAX_SANE_AMOUNT = "1000000.00"  # hard validation ceiling for any amount input


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (no extra dependency). Real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    frontend_url: str = "http://localhost:5173"
    approval_ttl_seconds: int = 600
    paypal_timeout_seconds: float = 10.0
    extra: dict = field(default_factory=dict)

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'outprovenance.db').as_posix()}"

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_api_key and self.ai_base_url and self.ai_model)


def load_settings() -> Settings:
    _load_dotenv(BACKEND_DIR / ".env")
    data_dir = Path(os.environ.get("OPP_DATA_DIR", "./data"))
    if not data_dir.is_absolute():
        data_dir = BACKEND_DIR / data_dir
    origins = os.environ.get("OPP_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        data_dir=data_dir,
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        paypal_client_id=os.environ.get("PAYPAL_CLIENT_ID", ""),
        paypal_client_secret=os.environ.get("PAYPAL_CLIENT_SECRET", ""),
        paypal_base_url=os.environ.get("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com").rstrip("/"),
        ai_api_key=os.environ.get("AI_API_KEY", ""),
        ai_base_url=os.environ.get("AI_BASE_URL", "").rstrip("/"),
        ai_model=os.environ.get("AI_MODEL", ""),
        frontend_url=os.environ.get("OPP_FRONTEND_URL", "http://localhost:5173").rstrip("/"),
    )
