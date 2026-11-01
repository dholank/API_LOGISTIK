import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from api_logistik import preflight


@pytest.fixture
def metadata():
    def number(table, name, precision=None, scale=None, nullable="Y", identity="NO"):
        return [table, name, "NUMBER", 22, precision, scale, nullable, None, identity]

    def text(table, name, size, nullable="Y"):
        return [table, name, "VARCHAR2", size, None, None, nullable, "B", "NO"]

    def timestamp(table, name, nullable="Y"):
        return [table, name, "TIMESTAMP(6) WITH TIME ZONE", 13, None, 6, nullable, None, "NO"]

    columns = [
        number("KARYAWAN", "ID_KARYAWAN", 5, 0, "N"),
        text("KARYAWAN", "NAMA", 50),
        text("KARYAWAN", "CABANG", 30),
        text("KARYAWAN", "NO_TELP", 20),
        text("KARYAWAN", "STATUS", 10),
        number("API_KEY_AUTH", "KEY_ID", nullable="N", identity="YES"),
        text("API_KEY_AUTH", "KEY_HASH", 64, "N"),
        text("API_KEY_AUTH", "STATUS", 10, "N"),
        timestamp("API_KEY_AUTH", "CREATED_AT", "N"),
        timestamp("API_KEY_AUTH", "ACTIVATES_AT"),
        timestamp("API_KEY_AUTH", "EXPIRES_AT"),
        text("API_KEY_ROTATION_STATE", "SCOPE_ID", 6, "N"),
        number("API_KEY_ROTATION_STATE", "ACTIVE_KEY_ID"),
        number("API_KEY_ROTATION_STATE", "GRACE_KEY_ID"),
        number("API_KEY_ROTATION_STATE", "PENDING_KEY_ID"),
        timestamp("API_KEY_ROTATION_STATE", "NEXT_ROTATION_AT"),
        timestamp("API_KEY_ROTATION_STATE", "PENDING_READY_AT"),
        number("API_KEY_ROTATION_STATE", "VERSION", 19, 0, "N"),
        text("API_KEY_ROTATION_STATE", "LAST_OPERATION_ID", 64),
        timestamp("API_KEY_ROTATION_STATE", "LAST_OPERATION_AT"),
    ]
    definitions = [
        ("KARYAWAN", "PK_KARYAWAN", "P", "ID_KARYAWAN"),
        ("API_KEY_AUTH", "PK_API_KEY_AUTH", "P", "KEY_ID"),
        ("API_KEY_AUTH", "UK_API_KEY_AUTH_HASH", "U", "KEY_HASH"),
        ("API_KEY_AUTH", "CK_API_KEY_AUTH_HASH", "C", None),
        ("API_KEY_AUTH", "CK_API_KEY_AUTH_STATUS", "C", None),
        ("API_KEY_AUTH", "CK_API_KEY_AUTH_LIVE_DATES", "C", None),
        ("API_KEY_AUTH", "CK_API_KEY_AUTH_WINDOW", "C", None),
        ("API_KEY_ROTATION_STATE", "PK_API_KEY_ROTATION_STATE", "P", "SCOPE_ID"),
        ("API_KEY_ROTATION_STATE", "CK_API_KEY_STATE_SCOPE", "C", None),
        ("API_KEY_ROTATION_STATE", "CK_API_KEY_STATE_VERSION", "C", None),
        ("API_KEY_ROTATION_STATE", "CK_API_KEY_STATE_READY", "C", None),
        ("API_KEY_ROTATION_STATE", "CK_API_KEY_STATE_NEXT", "C", None),
        ("API_KEY_ROTATION_STATE", "CK_API_KEY_STATE_OPERATION", "C", None),
        ("API_KEY_ROTATION_STATE", "CK_API_KEY_STATE_POINTERS", "C", None),
        ("API_KEY_ROTATION_STATE", "FK_API_KEY_STATE_ACTIVE", "R", "ACTIVE_KEY_ID"),
        ("API_KEY_ROTATION_STATE", "FK_API_KEY_STATE_GRACE", "R", "GRACE_KEY_ID"),
        ("API_KEY_ROTATION_STATE", "FK_API_KEY_STATE_PENDING", "R", "PENDING_KEY_ID"),
    ]
    return SimpleNamespace(
        objects=[
            ["KARYAWAN", "TABLE", "VALID"],
            ["API_KEY_AUTH", "TABLE", "VALID"],
            ["API_KEY_ROTATION_STATE", "TABLE", "VALID"],
            ["F_CRUD_KARYAWAN_LOGISTIK", "FUNCTION", "VALID"],
        ],
        columns=columns,
        constraints=[
            [table, name, kind, "ENABLED", "VALIDATED", "PK_API_KEY_AUTH" if kind == "R" else None]
            for table, name, kind, _ in definitions
        ],
        key_columns=[
            [table, name, column] for table, name, _, column in definitions if column is not None
        ],
        arguments=[
            [None, 0, "CLOB", "OUT", "N"],
            ["P_MODE", 1, "VARCHAR2", "IN", "N"],
            ["P_ID_KARYAWAN", 2, "NUMBER", "IN", "N"],
            ["P_NAMA", 3, "VARCHAR2", "IN", "Y"],
            ["P_CABANG", 4, "VARCHAR2", "IN", "Y"],
            ["P_NO_TELP", 5, "VARCHAR2", "IN", "Y"],
            ["P_STATUS", 6, "VARCHAR2", "IN", "Y"],
        ],
        charset="AL32UTF8",
        global_rows=1,
    )


class MetadataCursor:
    def __init__(self, metadata):
        self.metadata = metadata
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql):
        for view, attribute in (
            ("ALL_OBJECTS", "objects"),
            ("ALL_TAB_COLUMNS", "columns"),
            ("ALL_CONSTRAINTS", "constraints"),
            ("ALL_CONS_COLUMNS", "key_columns"),
            ("ALL_ARGUMENTS", "arguments"),
        ):
            if f"FROM {view}" in sql:
                self.rows = getattr(self.metadata, attribute)
                return
        if "FROM SESSION_PRIVS" in sql:
            self.rows = [("CREATE SESSION",)]
        elif "FROM NLS_DATABASE_PARAMETERS" in sql:
            self.rows = [(self.metadata.charset,)]
        elif "FROM API_KEY_ROTATION_STATE" in sql:
            if not any(
                row[:2] == ["API_KEY_ROTATION_STATE", "SCOPE_ID"] for row in self.metadata.columns
            ):
                raise RuntimeError("Cannot query a missing SCOPE_ID")
            self.rows = [(self.metadata.global_rows,)]
        else:
            raise AssertionError("Unexpected metadata query")

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]


class MetadataPool:
    def __init__(self, metadata):
        self.metadata = metadata

    @contextmanager
    def connection(self):
        yield SimpleNamespace(version="19.26.0.0.0", cursor=lambda: MetadataCursor(self.metadata))

    def close(self):
        pass


@pytest.fixture
def run_preflight(metadata, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "PoolManager", lambda settings: MetadataPool(metadata))
    monkeypatch.setattr(preflight, "load_settings", lambda path: None)
    monkeypatch.setattr(preflight, "configure_logging", lambda: None)

    def run():
        exit_code = preflight.main([])
        return exit_code, json.loads(capsys.readouterr().out)

    return run


def test_canonical_metadata_allows_further_integration_without_claiming_live_dml(run_preflight):
    exit_code, report = run_preflight()
    assert exit_code == 0
    assert report["ready_for_further_integration"] is True
    assert report["schema_issues"] == []
    assert report["live_dml_and_function_behavior_tested"] is False


@pytest.mark.parametrize(
    "table,column,field,value,issue",
    [
        ("API_KEY_AUTH", "ACTIVATES_AT", 1, "ACTIVE_AT", "COLUMN_MISSING"),
        ("API_KEY_AUTH", "EXPIRES_AT", 2, "TIMESTAMP(6)", "COLUMN_DEFINITION"),
        ("KARYAWAN", "ID_KARYAWAN", 4, None, "COLUMN_DEFINITION"),
        ("API_KEY_ROTATION_STATE", "VERSION", 5, None, "COLUMN_DEFINITION"),
        ("API_KEY_AUTH", "KEY_HASH", 6, "Y", "COLUMN_DEFINITION"),
        ("KARYAWAN", "NAMA", 3, 200, "COLUMN_BYTE_LENGTH"),
        ("KARYAWAN", "STATUS", 7, "C", "COLUMN_BYTE_LENGTH"),
        ("API_KEY_AUTH", "KEY_ID", 8, "NO", "COLUMN_IDENTITY"),
    ],
)
def test_incompatible_column_metadata_blocks_readiness(
    metadata, run_preflight, table, column, field, value, issue
):
    row = next(row for row in metadata.columns if row[:2] == [table, column])
    row[field] = value
    exit_code, report = run_preflight()
    assert exit_code == 2 and report["ready_for_further_integration"] is False
    assert f"{issue}:{table}.{column}" in report["schema_issues"]


def test_missing_scope_column_is_reported_without_querying_it(metadata, run_preflight):
    metadata.columns = [
        row for row in metadata.columns if row[:2] != ["API_KEY_ROTATION_STATE", "SCOPE_ID"]
    ]
    exit_code, report = run_preflight()
    assert exit_code == 2
    assert "COLUMN_MISSING:API_KEY_ROTATION_STATE.SCOPE_ID" in report["schema_issues"]
    assert report["global_state_rows"] is None


def test_unexpected_legacy_required_column_blocks_readiness(metadata, run_preflight):
    metadata.columns.append(
        ["API_KEY_AUTH", "CLIENT_ID", "VARCHAR2", 64, None, None, "N", "B", "NO"]
    )
    exit_code, report = run_preflight()
    assert exit_code == 2 and report["ready_for_further_integration"] is False
    assert "COLUMN_UNEXPECTED:API_KEY_AUTH.CLIENT_ID" in report["schema_issues"]


@pytest.mark.parametrize("field,value", [(2, "U"), (3, "DISABLED"), (4, "NOT VALIDATED")])
def test_incompatible_constraint_metadata_blocks_readiness(metadata, run_preflight, field, value):
    row = next(row for row in metadata.constraints if row[1] == "CK_API_KEY_AUTH_STATUS")
    row[field] = value
    exit_code, report = run_preflight()
    assert exit_code == 2 and report["ready_for_further_integration"] is False
    assert "CONSTRAINT_DEFINITION:API_KEY_AUTH.CK_API_KEY_AUTH_STATUS" in report["schema_issues"]


def test_missing_unique_constraint_blocks_readiness(metadata, run_preflight):
    metadata.constraints = [row for row in metadata.constraints if row[1] != "UK_API_KEY_AUTH_HASH"]
    exit_code, report = run_preflight()
    assert exit_code == 2
    assert "CONSTRAINT_MISSING:API_KEY_AUTH.UK_API_KEY_AUTH_HASH" in report["schema_issues"]


def test_unique_constraint_on_wrong_column_blocks_readiness(metadata, run_preflight):
    row = next(row for row in metadata.key_columns if row[1] == "UK_API_KEY_AUTH_HASH")
    row[2] = "KEY_ID"
    exit_code, report = run_preflight()
    assert exit_code == 2
    assert "CONSTRAINT_COLUMNS:API_KEY_AUTH.UK_API_KEY_AUTH_HASH" in report["schema_issues"]


def test_foreign_key_outside_canonical_owner_or_target_blocks_readiness(metadata, run_preflight):
    row = next(row for row in metadata.constraints if row[1] == "FK_API_KEY_STATE_PENDING")
    row[5] = None
    exit_code, report = run_preflight()
    assert exit_code == 2
    assert (
        "CONSTRAINT_REFERENCE:API_KEY_ROTATION_STATE.FK_API_KEY_STATE_PENDING"
        in report["schema_issues"]
    )


@pytest.mark.parametrize(
    "position,field,value",
    [(0, 2, "VARCHAR2"), (2, 2, "VARCHAR2"), (3, 0, "WRONG_NAME"), (4, 3, "OUT"), (5, 4, "N")],
)
def test_function_signature_mismatch_blocks_readiness(
    metadata, run_preflight, position, field, value
):
    metadata.arguments[position][field] = value
    exit_code, report = run_preflight()
    assert exit_code == 2 and report["ready_for_further_integration"] is False
    assert "FUNCTION_SIGNATURE:F_CRUD_KARYAWAN_LOGISTIK" in report["schema_issues"]


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_wrong_object_type_blocks_readiness(metadata, run_preflight, missing):
    if missing:
        metadata.objects.pop()
    else:
        metadata.objects[-1][1] = "PACKAGE"
    exit_code, report = run_preflight()
    assert exit_code == 2 and report["ready_for_further_integration"] is False
    assert "F_CRUD_KARYAWAN_LOGISTIK" in report["missing_objects"]


@pytest.mark.parametrize("attribute,value", [("charset", "WE8MSWIN1252"), ("global_rows", 0)])
def test_charset_or_singleton_mismatch_blocks_readiness(metadata, run_preflight, attribute, value):
    setattr(metadata, attribute, value)
    exit_code, report = run_preflight()
    assert exit_code == 2 and report["ready_for_further_integration"] is False
