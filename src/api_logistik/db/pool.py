import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any, cast

import oracledb

from api_logistik.config import Settings
from api_logistik.errors import CommitOutcomeUnknown, DatabaseUnavailable

_MODE_LOCK = Lock()
_LOG = logging.getLogger("api_logistik.database")


class PoolManager:
    def __init__(
        self,
        settings: Settings,
        *,
        writer: bool = False,
        pool_factory: Callable[..., Any] = oracledb.create_pool,
    ) -> None:
        self.settings = settings
        self.writer = writer
        self._factory = pool_factory
        self._pool: Any = None
        self._lock = Lock()
        self._closed = False

    def _get_pool(self) -> Any:
        with self._lock:
            if self._closed:
                raise DatabaseUnavailable()
            if self._pool is not None:
                return self._pool
            s = self.settings
            if not (s.oracle_dsn and s.oracle_user and s.oracle_password):
                raise DatabaseUnavailable()
            try:
                with _MODE_LOCK:
                    if s.oracle_mode == "thick":
                        oracledb.init_oracle_client(lib_dir=str(s.oracle_client_lib_dir))
                    else:
                        cast(Callable[[], None], oracledb.enable_thin_mode)()
                params = oracledb.PoolParams()
                params.parse_connect_string(s.oracle_dsn.get_secret_value())
                if params.protocol != "tcps":
                    raise DatabaseUnavailable()
                options: dict[str, Any] = {
                    "min": s.oracle_pool_min if not self.writer else 1,
                    "max": s.oracle_pool_max if not self.writer else 1,
                    "increment": s.oracle_pool_increment,
                    "getmode": oracledb.POOL_GETMODE_TIMEDWAIT,
                    "wait_timeout": s.oracle_pool_wait_ms,
                    "tcp_connect_timeout": s.oracle_connect_timeout,
                    "retry_count": 0,
                    "ssl_server_dn_match": True,
                }
                if s.oracle_wallet_dir:
                    options.update(
                        config_dir=str(s.oracle_wallet_dir),
                        wallet_location=str(s.oracle_wallet_dir),
                    )
                if s.oracle_wallet_password:
                    options["wallet_password"] = s.oracle_wallet_password.get_secret_value()
                params.set(**options)
                user = (
                    s.oracle_writer_user if self.writer and s.oracle_writer_user else s.oracle_user
                )
                password = (
                    s.oracle_writer_password
                    if self.writer and s.oracle_writer_password
                    else s.oracle_password
                )
                self._pool = self._factory(
                    user=user.get_secret_value(),
                    password=password.get_secret_value(),
                    params=params,
                )
                return self._pool
            except oracledb.Error, ValueError, OSError:
                raise DatabaseUnavailable() from None

    @contextmanager
    def connection(self) -> Iterator[Any]:
        pool = self._get_pool()
        try:
            connection = pool.acquire()
        except oracledb.Error:
            raise DatabaseUnavailable() from None
        dropped = False
        try:
            try:
                connection.call_timeout = self.settings.oracle_call_timeout_ms
            except oracledb.Error:
                dropped = True
                pool.drop(connection)
                raise DatabaseUnavailable() from None
            try:
                yield connection
            except CommitOutcomeUnknown:
                dropped = True
                try:
                    pool.drop(connection)
                except oracledb.Error:
                    _LOG.warning("uncertain_connection_drop_failed")
                raise
        finally:
            if not dropped:
                try:
                    pool.release(connection)
                except oracledb.Error:
                    try:
                        pool.drop(connection)
                    except oracledb.Error:
                        pass
                    _LOG.warning("connection_release_failed")

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._pool is not None:
                try:
                    self._pool.close(force=True)
                except oracledb.Error:
                    _LOG.warning("pool_shutdown_failed")
                self._pool = None
