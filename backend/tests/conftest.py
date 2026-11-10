"""Test fixtures: every test gets a fresh temp data dir, so real local data/keys are never touched."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def db(app):
    session = app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
