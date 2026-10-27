from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import oracledb

from api_logistik.errors import CommitOutcomeUnknown, DatabaseUnavailable


@contextmanager
def transaction(connection: Any, *, write: bool = True) -> Iterator[None]:
    try:
        yield
    except BaseException:
        try:
            connection.rollback()
        except oracledb.Error:
            pass
        raise
    else:
        if write:
            try:
                connection.commit()
            except oracledb.Error:
                raise CommitOutcomeUnknown() from None
        else:
            try:
                connection.rollback()
            except oracledb.Error:
                raise DatabaseUnavailable() from None
