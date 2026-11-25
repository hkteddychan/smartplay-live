"""Settings and constants for the SmartPLAY poller.

All times are Hong Kong time (UTC+08:00).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Smallest payload first: this order keeps each cycle cheap and fast.
SPORTS: list[str] = [
    "turf-soccer-pitch",
    "tennis",
    "basketball",
    "volleyball",
    "badminton",
]

ACTIVITY = "activity-prog"

CYCLE_SECONDS = 60
STAGGER_SECONDS = 8
ACTIVITY_EVERY_SECONDS = 300


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    tg_token: str
    tg_chat: str
    tg_thread: int
    ntfy_url: str
    r2_endpoint: str
    r2_bucket: str
    r2_access_key: str
    r2_secret_key: str
    db_path: str

    @classmethod
    def from_env(cls) -> Settings:
        tg_token = os.environ.get("TG_TOKEN", "").strip()
        if not tg_token:
            raise ConfigError("TG_TOKEN is required")

        return cls(
            tg_token=tg_token,
            tg_chat=os.environ.get("TG_CHAT", "5200360037"),
            tg_thread=int(os.environ.get("TG_THREAD", "68130")),
            ntfy_url=os.environ.get("NTFY_URL", ""),
            r2_endpoint=os.environ.get("R2_ENDPOINT", ""),
            r2_bucket=os.environ.get("R2_BUCKET", ""),
            r2_access_key=os.environ.get("R2_ACCESS_KEY", ""),
            r2_secret_key=os.environ.get("R2_SECRET_KEY", ""),
            db_path=os.environ.get("DB_PATH", "/opt/smartplay/state.db"),
        )
