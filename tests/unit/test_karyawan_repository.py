import json
from types import SimpleNamespace
from unittest.mock import Mock

import oracledb
import pytest

from api_logistik.db.karyawan_repository import KaryawanRepository
from api_logistik.errors import DatabaseContractError, DatabaseUnavailable


def success(identifier=1):
    return {
        "success": True,
        "code": "SUCCESS",
        "message": "Synthetic result",
        "data": {"id_karyawan": identifier, "no_telp": "001"},
    }


@pytest.fixture
def repository_setup():
    output = Mock()
    output.getvalue.return_value = json.dumps(success())
    cursor = Mock()
    cursor.var.return_value = output
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    connection = Mock()
    connection.cursor.return_value = cursor
    return KaryawanRepository(connection), connection, cursor, output


@pytest.mark.parametrize("mode", ["CREATE", "READ", "UPDATE", "DELETE"])
def test_repository_calls_plsql_function_with_numeric_id_and_bound_fields(repository_setup, mode):
    repository, connection, cursor, _ = repository_setup
    fields = {"nama": "Synthetic ' :name", "cabang": "Test", "no_telp": "001", "status": "AKTIF"}
    result = repository.call(mode, "00001", fields)
    block = cursor.execute.call_args.args[0]
    binds = cursor.execute.call_args.kwargs
    assert block.strip().startswith("BEGIN")
    assert "F_CRUD_KARYAWAN_LOGISTIK(" in block
    assert "SELECT" not in block.upper()
    assert "Synthetic" not in block
    assert binds == {"result": cursor.var.return_value, "mode": mode, "identifier": 1, **fields}
    assert type(binds["identifier"]) is int
    cursor.var.assert_called_once_with(oracledb.DB_TYPE_CLOB)
    assert result.data.id_karyawan == "1"
    assert result.data.no_telp == "001"
    cursor.__exit__.assert_called_once()
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


@pytest.mark.parametrize(
    "identifier,normalized", [(0, "0"), (99999, "99999"), ("00001", "1"), ("00000", "0")]
)
def test_parser_normalizes_numeric_or_zero_padded_id(repository_setup, identifier, normalized):
    repository, _, _, output = repository_setup
    output.getvalue.return_value = json.dumps(success(identifier))
    assert repository.call("READ", normalized).data.id_karyawan == normalized


def test_repository_reads_clob_before_cursor_closes(repository_setup, monkeypatch):
    import api_logistik.db.karyawan_repository as module

    repository, _, cursor, output = repository_setup
    events = []

    class FakeLOB:
        def read(self):
            events.append("read")
            return json.dumps(success())

    monkeypatch.setattr(module.oracledb, "LOB", FakeLOB)
    output.getvalue.return_value = FakeLOB()
    cursor.__exit__.side_effect = lambda *args: events.append("close")
    assert repository.call("READ", "1").success
    assert events == ["read", "close"]


@pytest.mark.parametrize(
    "raw",
    [
        None,
        b"{}",
        "not json",
        pytest.param("x" * 65537, id="oversized-output"),
        '{"success": true}',
        json.dumps({**success(), "success": "true"}),
        json.dumps({**success(), "code": "KRY_001"}),
        json.dumps({**success(), "data": None}),
        json.dumps({**success(), "unexpected": "private-marker"}),
        json.dumps(success(2)),
        json.dumps(success(True)),
        json.dumps(success("１２")),
        json.dumps(success("123456")),
        json.dumps(success(1.0)),
        json.dumps(
            {
                "success": False,
                "code": "KRY_001",
                "message": "Synthetic",
                "data": {"id_karyawan": 1},
            }
        ),
    ],
)
def test_malformed_or_inconsistent_oracle_response_is_safe_contract_error(repository_setup, raw):
    repository, connection, cursor, output = repository_setup
    output.getvalue.return_value = raw
    with pytest.raises(DatabaseContractError) as caught:
        repository.call("READ", "1")
    assert caught.value.status_code == 500
    assert "private-marker" not in str(caught.value)
    cursor.__exit__.assert_called_once()
    connection.commit.assert_not_called()


@pytest.mark.parametrize("code", ["KRY_001", "KRY_404", "UNKNOWN"])
def test_parser_preserves_false_for_transaction_owner(repository_setup, code):
    repository, connection, _, output = repository_setup
    output.getvalue.return_value = json.dumps(
        {"success": False, "code": code, "message": "Synthetic failure", "data": None}
    )
    result = repository.call("DELETE", "1")
    assert result.success is False
    assert result.code == code
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


@pytest.mark.parametrize(
    "code,error",
    [
        ("ORA-03113", DatabaseUnavailable),
        ("DPY-4011", DatabaseUnavailable),
        ("ORA-00942", DatabaseContractError),
    ],
)
def test_driver_failures_are_classified_without_raw_details(repository_setup, code, error):
    repository, connection, cursor, _ = repository_setup
    cursor.execute.side_effect = oracledb.DatabaseError(
        SimpleNamespace(full_code=code, message="synthetic-driver-private")
    )
    with pytest.raises(error) as caught:
        repository.call("READ", "1")
    assert "synthetic-driver-private" not in str(caught.value)
    cursor.__exit__.assert_called_once()
    connection.commit.assert_not_called()


def test_invalid_mode_never_opens_cursor(repository_setup):
    repository, connection, _, _ = repository_setup
    with pytest.raises(DatabaseContractError):
        repository.call("UPSERT", "1")
    connection.cursor.assert_not_called()
