from pathlib import Path

import pytest

from Src.db.Src import database as db
from Src.db.Src.models import Base


@pytest.fixture
def isolated_database(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.configure_database(str(db_path))
    Base.metadata.create_all(db.engine)
    yield db
    db.engine.dispose()


@pytest.fixture(autouse=True)
def disable_live_gitlab_role_checks(monkeypatch):
    monkeypatch.setenv("GITLAB_ENFORCE_COMMAND_ROLES", "false")
