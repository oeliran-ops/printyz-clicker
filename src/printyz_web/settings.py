"""Site settings from environment variables (see deploy/.env.example). No secrets in code."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    site_name: str = field(default_factory=lambda: _env("PRINTYZ_SITE_NAME", "Printyz"))
    base_url: str = field(default_factory=lambda: _env("PRINTYZ_BASE_URL", "http://localhost:8000").rstrip("/"))
    data_dir: Path = field(default_factory=lambda: Path(_env("PRINTYZ_DATA_DIR", "./site-data")).resolve())
    admin_password: str = field(default_factory=lambda: _env("PRINTYZ_ADMIN_PASSWORD"))
    secret_key: str = field(default_factory=lambda: _env("PRINTYZ_SECRET_KEY") or secrets.token_hex(32))
    owner_email: str = field(default_factory=lambda: _env("PRINTYZ_OWNER_EMAIL"))
    owner_whatsapp: str = field(default_factory=lambda: _env("PRINTYZ_OWNER_WHATSAPP"))      # e.g. 9725XXXXXXXX
    callmebot_apikey: str = field(default_factory=lambda: _env("PRINTYZ_CALLMEBOT_APIKEY"))  # optional, free
    smtp_host: str = field(default_factory=lambda: _env("PRINTYZ_SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("PRINTYZ_SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("PRINTYZ_SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("PRINTYZ_SMTP_PASSWORD"))
    mail_from: str = field(default_factory=lambda: _env("PRINTYZ_MAIL_FROM"))
    email_backend: str = field(default_factory=lambda: _env("PRINTYZ_EMAIL_BACKEND", "smtp"))  # smtp | memory | console
    workers: int = field(default_factory=lambda: int(_env("PRINTYZ_GEOMETRY_WORKERS", "2")))

    def __post_init__(self) -> None:
        for sub in ("orders", "uploads"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "printyz.sqlite3"
