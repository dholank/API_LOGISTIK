import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock

import oracledb
import pytest

from api_logistik.config import Settings
from api_logistik.db.pool import PoolManager
from api_logistik.errors import DatabaseUnavailable


@pytest.fixture
def pool_setup(monkeypatch):
    import api_logistik.db.pool as module

    for name in tuple(os.environ):
        if name.lower() in Settings.model_fields:
            monkeypatch.delenv(name)
    params = Mock(protocol="tcps")
    monkeypatch.setattr(module.oracledb, "PoolParams", Mock(return_value=params))
    thin = Mock()
    thick = Mock()
    monkeypatch.setattr(module.oracledb, "enable_thin_mode", thin)
    monkeypatch.setattr(module.oracledb, "init_oracle_client", thick)
    settings = Settings(
        _env_file=None,
        environment="test",
        oracle_dsn="tcps://synthetic.invalid:2484/test",
        oracle_user="synthetic_user",
        oracle_password="synthetic-password",
        oracle_pool_min=2,
        oracle_pool_max=4,
        oracle_pool_wait_ms=1234,
        oracle_connect_timeout=3,
        oracle_call_timeout_ms=4321,
    )
    pool = Mock()
    pool.acquire.return_value = Mock()
    factory = Mock(return_value=pool)
    return settings, pool, factory, params, thin, thick


def test_pool_is_lazy_and_uses_bounded_capacity_timeouts_and_no_retries(pool_setup):
    settings, pool, factory, params, thin, thick = pool_setup
    manager = PoolManager(settings, pool_factory=factory)
    factory.assert_not_called()
    thin.assert_not_called()
    thick.assert_not_called()
    with manager.connection() as connection:
        assert connection.call_timeout == 4321
    thin.assert_called_once_with()
    thick.assert_not_called()
    params.parse_connect_string.assert_called_once_with("tcps://synthetic.invalid:2484/test")
    options = params.set.call_args.kwargs
    assert options == {
        "min": 2,
        "max": 4,
        "increment": 1,
        "getmode": oracledb.POOL_GETMODE_TIMEDWAIT,
        "wait_timeout": 1234,
        "tcp_connect_timeout": 3.0,
        "retry_count": 0,
        "ssl_server_dn_match": True,
    }
    factory.assert_called_once_with(
        user="synthetic_user", password="synthetic-password", params=params
    )
    pool.release.assert_called_once_with(connection)


def test_concurrent_pool_access_creates_exactly_one_instance(pool_setup):
    settings, pool, factory, _, _, _ = pool_setup
    manager = PoolManager(settings, pool_factory=factory)
    barrier = Barrier(8)

    def obtain():
        barrier.wait(timeout=5)
        return manager._get_pool()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: obtain(), range(8)))
    assert all(result is pool for result in results)
    factory.assert_called_once()


def test_thick_mode_requires_explicit_client_and_never_falls_back(pool_setup):
    settings, _, factory, _, thin, thick = pool_setup
    settings = settings.model_copy(
        update={"oracle_mode": "thick", "oracle_client_lib_dir": "synthetic-client"}
    )
    thick.side_effect = oracledb.DatabaseError("synthetic-client-failure")
    manager = PoolManager(settings, pool_factory=factory)
    with pytest.raises(DatabaseUnavailable):
        manager._get_pool()
    thick.assert_called_once_with(lib_dir="synthetic-client")
    thin.assert_not_called()
    factory.assert_not_called()


def test_writer_pool_is_one_connection_with_explicit_writer_credentials(pool_setup):
    settings, _, factory, params, _, _ = pool_setup
    settings = settings.model_copy(
        update={
            "oracle_writer_user": settings.oracle_user,
            "oracle_writer_password": settings.oracle_password,
        }
    )
    manager = PoolManager(settings, writer=True, pool_factory=factory)
    manager._get_pool()
    assert params.set.call_args.kwargs["min"] == 1
    assert params.set.call_args.kwargs["max"] == 1


def test_shutdown_is_idempotent_and_prevents_reopening(pool_setup):
    settings, pool, factory, _, _, _ = pool_setup
    manager = PoolManager(settings, pool_factory=factory)
    manager._get_pool()
    manager.close()
    manager.close()
    pool.close.assert_called_once_with(force=True)
    with pytest.raises(DatabaseUnavailable):
        manager._get_pool()
    factory.assert_called_once()


def test_acquire_failure_is_safe_and_does_not_release_nonexistent_connection(pool_setup):
    settings, pool, factory, _, _, _ = pool_setup
    pool.acquire.side_effect = oracledb.DatabaseError("synthetic-acquire-secret")
    manager = PoolManager(settings, pool_factory=factory)
    with pytest.raises(DatabaseUnavailable) as caught, manager.connection():
        pytest.fail("Acquire failure must not enter context")
    assert "synthetic-acquire-secret" not in str(caught.value)
    pool.release.assert_not_called()


def test_call_timeout_assignment_failure_cleans_up_acquired_connection(pool_setup):
    settings, pool, factory, _, _, _ = pool_setup

    class BrokenTimeoutConnection:
        @property
        def call_timeout(self):
            return 0

        @call_timeout.setter
        def call_timeout(self, value):
            raise oracledb.DatabaseError("synthetic-timeout-setting-failure")

    connection = BrokenTimeoutConnection()
    pool.acquire.return_value = connection
    manager = PoolManager(settings, pool_factory=factory)
    with pytest.raises(DatabaseUnavailable), manager.connection():
        pytest.fail("Timeout assignment failure must not enter context")
    assert pool.release.call_count + pool.drop.call_count == 1
    cleanup = pool.release if pool.release.called else pool.drop
    cleanup.assert_called_once_with(connection)


def test_release_failure_drops_connection_and_logs_no_driver_details(pool_setup, caplog):
    settings, pool, factory, _, _, _ = pool_setup
    pool.release.side_effect = oracledb.DatabaseError("synthetic-release-secret")
    manager = PoolManager(settings, pool_factory=factory)
    with manager.connection() as connection:
        pass
    pool.drop.assert_called_once_with(connection)
    assert "connection_release_failed" in caplog.text
    assert "synthetic-release-secret" not in caplog.text


def test_connection_released_even_when_caller_raises(pool_setup):
    settings, pool, factory, _, _, _ = pool_setup
    manager = PoolManager(settings, pool_factory=factory)
    with pytest.raises(RuntimeError), manager.connection() as connection:
        raise RuntimeError("synthetic-caller-failure")
    pool.release.assert_called_once_with(connection)
