from datetime import UTC, datetime
from pathlib import Path

import pytest

from rider_agent.config import Settings
from rider_agent.db import Database

IST_NOON = datetime(2026, 10, 26, 6, 30, tzinfo=UTC)  # 12:00 IST on a Monday


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        backend_api_key="test-key",
        db_path=tmp_path / "test.db",
        sarvam_api_key="sarvam-test",
        sarvam_org_id="org1",
        sarvam_workspace_id="ws1",
        sarvam_app_id="app1",
        sarvam_connection_id="conn1",
        sarvam_agent_phone_number="+918000000000",
        public_base_url="https://example.test",
    )


@pytest.fixture
def db(settings: Settings) -> Database:
    database = Database(settings.db_path)
    database.init_schema()
    return database


@pytest.fixture
def now() -> datetime:
    return IST_NOON
