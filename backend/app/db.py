"""SQLite engine and session helper."""
from __future__ import annotations

import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

DB_PATH = Path(os.getenv("SPENDGUARD_DB", Path(__file__).resolve().parent.parent / "spendguard.db"))
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db(eng=None) -> None:
    from . import models  # noqa: F401  (register tables)
    SQLModel.metadata.create_all(eng or engine)


def get_session(eng=None) -> Session:
    return Session(eng or engine)
