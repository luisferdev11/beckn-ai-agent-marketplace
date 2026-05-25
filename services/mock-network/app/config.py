"""Mock-network configuration — env-driven, no defaults that hide misconfig.

Reading these at import time would crash the test suite when DB_* are not
set. We read at call time and validate explicitly to keep tests trivially
runnable without a real Postgres.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


SERVICE_NAME = os.getenv("SERVICE_NAME", "mock-network")
PORT = int(os.getenv("PORT", "8090"))


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


def load_db_config() -> DatabaseConfig:
    """Read DB env vars; raise if any required value is missing.

    Kept as a function (not a module-level constant) so test fixtures
    can monkeypatch env between tests without import-order surprises.
    """
    return DatabaseConfig(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5436")),
        name=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
