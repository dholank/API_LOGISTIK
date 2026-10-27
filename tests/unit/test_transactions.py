from unittest.mock import Mock

import oracledb
import pytest

from api_logistik.db.transactions import transaction
from api_logistik.errors import CommitOutcomeUnknown, DatabaseContractError, DatabaseUnavailable


@pytest.mark.parametrize("write", [False, True])
def test_transaction_finishes_with_explicit_read_or_write_policy(write):
    connection = Mock()
    with transaction(connection, write=write):
        connection.commit.assert_not_called()
        connection.rollback.assert_not_called()
    assert connection.commit.call_count == int(write)
    assert connection.rollback.call_count == int(not write)


@pytest.mark.parametrize(
    "error",
    [
        DatabaseContractError(),
        ValueError("synthetic-parser"),
        oracledb.DatabaseError("synthetic-driver"),
        KeyboardInterrupt(),
    ],
)
def test_transaction_rolls_back_and_preserves_failure(error):
    connection = Mock()
    with pytest.raises(type(error)) as caught, transaction(connection):
        raise error
    assert caught.value is error
    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()


def test_rollback_driver_failure_does_not_replace_original_failure():
    connection = Mock()
    connection.rollback.side_effect = oracledb.DatabaseError("synthetic-rollback")
    error = DatabaseContractError()
    with pytest.raises(DatabaseContractError) as caught, transaction(connection):
        raise error
    assert caught.value is error
    connection.commit.assert_not_called()


def test_commit_failure_never_retries_or_claims_rollback_cancels_commit():
    connection = Mock()
    connection.commit.side_effect = oracledb.DatabaseError("synthetic-commit")
    with pytest.raises(CommitOutcomeUnknown) as caught, transaction(connection):
        pass
    assert caught.value.status_code == 503
    assert caught.value.code == "COMMIT_OUTCOME_UNKNOWN"
    assert "synthetic-commit" not in str(caught.value)
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()


def test_read_cleanup_failure_is_database_unavailable():
    connection = Mock()
    connection.rollback.side_effect = oracledb.DatabaseError("synthetic-read-cleanup")
    with pytest.raises(DatabaseUnavailable), transaction(connection, write=False):
        pass
    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()
