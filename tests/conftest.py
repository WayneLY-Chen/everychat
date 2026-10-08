from pathlib import Path

import pytest

from everychat.db import Database

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def db(tmp_path: Path) -> Database:
    with Database(tmp_path / "test.db") as database:
        yield database
