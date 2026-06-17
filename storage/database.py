from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


DATABASE_FILE = Path(__file__).resolve().parent.parent / ".agent_memory" / "agent.db"
_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


def get_database_path() -> Path:
    return DATABASE_FILE


def _database_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def configure_database(path: Path | str) -> None:
    global DATABASE_FILE, _ENGINE, _SESSION_FACTORY
    DATABASE_FILE = Path(path)
    _ENGINE = None
    _SESSION_FACTORY = None


def clear_database() -> None:
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SESSION_FACTORY = None
    if DATABASE_FILE.exists():
        DATABASE_FILE.unlink()


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ENGINE = create_engine(_database_url(DATABASE_FILE), future=True)
    return _ENGINE


def get_session() -> Session:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)
    return _SESSION_FACTORY()


def init_db() -> None:
    from storage.models import Base

    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(get_engine())
