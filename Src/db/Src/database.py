import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import declarative_base, sessionmaker


Base = declarative_base()


def _create_engine(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )


DB_PATH = os.getenv("DB_PATH", "./db/findings.db")
engine = _create_engine(DB_PATH)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def configure_database(db_path: str) -> None:
    """Rebind database helpers. Intended for isolated tests and CLI tools."""
    global DB_PATH, engine, SessionLocal
    engine.dispose()
    DB_PATH = db_path
    engine = _create_engine(db_path)
    SessionLocal.configure(bind=engine)


def execute(sql: str, params: dict | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def query_one(sql: str, params: dict | None = None) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None


def query_all(sql: str, params: dict | None = None) -> list[dict]:
    with engine.begin() as conn:
        return [
            dict(row)
            for row in conn.execute(text(sql), params or {}).mappings().all()
        ]


def query_scalar(sql: str, params: dict | None = None):
    with engine.begin() as conn:
        return conn.execute(text(sql), params or {}).scalar()
