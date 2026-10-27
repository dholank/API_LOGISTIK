import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api_logistik.config import Settings
from api_logistik.main import create_app
from api_logistik.schemas.responses import OracleResponse
from api_logistik.security.api_keys import generate_api_key, hash_api_key
from api_logistik.security.key_rotation import KeyRecord, RotationState


class FakeConnection:
    def __init__(self, events):
        self.events = events
        self.commit_error = None

    def commit(self):
        self.events.append("commit")
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.events.append("rollback")


@pytest.fixture
def harness(monkeypatch):
    for name in tuple(os.environ):
        if name.lower() in Settings.model_fields:
            monkeypatch.delenv(name)
    events = []
    key = generate_api_key()
    activation = datetime(2026, 1, 1, tzinfo=UTC)
    record = KeyRecord(
        1, hash_api_key(key), "ACTIVE", activation, activation, activation + timedelta(days=8)
    )
    state = RotationState(active_key_id=1, next_rotation_at=activation + timedelta(days=7))
    app = create_app(Settings(_env_file=None, environment="test"))
    connection = FakeConnection(events)
    context = SimpleNamespace(
        app=app,
        key=key,
        events=events,
        connection=connection,
        record=record,
        state=state,
        now=activation + timedelta(days=1),
        auth_error=None,
        business_error=None,
        business_calls=[],
        digest=None,
        pool_error=None,
        result=OracleResponse(
            success=True, code="SUCCESS", message="Synthetic result", data={"id_karyawan": "1"}
        ),
    )

    class Pool:
        @contextmanager
        def connection(self):
            events.append("acquire")
            if context.pool_error:
                raise context.pool_error
            try:
                yield connection
            finally:
                events.append("release")

    class AuthRepository:
        def __init__(self, conn):
            assert conn is connection

        def lookup(self, digest):
            events.append("auth")
            context.digest = digest
            if context.auth_error:
                raise context.auth_error
            return context.record, context.state, context.now

    class BusinessRepository:
        def __init__(self, conn):
            assert conn is connection

        def call(self, mode, identifier, fields):
            events.append("business")
            context.business_calls.append((mode, identifier, fields))
            if context.business_error:
                raise context.business_error
            return context.result

    app.state.pool = Pool()
    app.state.auth_repository_factory = AuthRepository
    app.state.karyawan_repository_factory = BusinessRepository

    async def observe(scope, receive, send):
        async def observed_send(message):
            if message["type"] == "http.response.start":
                events.append("http_start")
            await send(message)

        await app(scope, receive, observed_send)

    with TestClient(observe, raise_server_exceptions=False) as client:
        context.client = client
        yield context


@pytest.fixture
def body():
    return {
        "id_karyawan": "00001",
        "nama": "Synthetic",
        "cabang": "Test",
        "no_telp": "001",
        "status": "AKTIF",
    }
