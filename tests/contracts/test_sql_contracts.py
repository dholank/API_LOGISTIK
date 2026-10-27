import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SQL_FILES = (
    "prechecks/Q_VERIFY_EXISTING_OBJECTS.sql",
    "prechecks/Q_VERIFY_API_KEY_STORAGE.sql",
    "schema/T_API_KEY_AUTH.sql",
    "schema/T_API_KEY_ROTATION_STATE.sql",
    "schema/C_API_KEY_AUTH_STATUS.sql",
    "seed/D_INIT_API_KEY_ROTATION_STATE.sql",
)


def sql_source(relative):
    source = (ROOT / "database" / relative).read_text(encoding="utf-8")
    return re.sub(r"--[^\n]*", "", source).upper()


@pytest.mark.parametrize("relative", SQL_FILES[:2])
def test_prechecks_are_read_only_and_do_not_select_key_material(relative):
    source = sql_source(relative)
    assert not re.search(
        r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|COMMIT|EXECUTE|BEGIN|CALL)\b", source
    )
    assert not re.search(r"\b(?:KEY_HASH|RAW_KEY|API_KEY_VALUE)\b", source)
    assert not re.search(r"SELECT\s+(?:\w+\.)?\*", source)


def test_auth_table_stores_unique_lower_hex_digest_and_utc_capable_timestamps():
    source = sql_source(SQL_FILES[2])
    assert "KEY_ID NUMBER GENERATED ALWAYS AS IDENTITY" in source
    assert "KEY_HASH VARCHAR2(64 BYTE) NOT NULL" in source
    assert "UNIQUE (KEY_HASH)" in source
    assert "LENGTH(KEY_HASH) = 64" in source
    assert "TRANSLATE(KEY_HASH, 'X0123456789ABCDEF', 'X') IS NULL" in source
    for column in ("CREATED_AT", "ACTIVATES_AT", "EXPIRES_AT"):
        assert re.search(rf"\b{column}\s+TIMESTAMP WITH TIME ZONE\b", source)
    assert "EXPIRES_AT > ACTIVATES_AT" in source
    for status in ("PENDING", "ACTIVE", "GRACE", "EXPIRED", "REVOKED"):
        assert f"'{status}'" in source


def test_state_schema_requires_single_global_scope_version_and_consistent_pointers():
    source = sql_source(SQL_FILES[3])
    assert "PRIMARY KEY (SCOPE_ID)" in source
    assert "CHECK (SCOPE_ID = 'GLOBAL')" in source
    assert "CHECK (VERSION >= 0)" in source
    assert "PENDING_READY_AT IS NULL OR PENDING_KEY_ID IS NOT NULL" in source
    for column in ("NEXT_ROTATION_AT", "PENDING_READY_AT", "LAST_OPERATION_AT"):
        assert re.search(rf"\b{column}\s+TIMESTAMP WITH TIME ZONE\b", source)
    for pointer in ("ACTIVE", "GRACE", "PENDING"):
        assert f"FOREIGN KEY ({pointer}_KEY_ID)" in source
    assert source.count("REFERENCES API_KEY_AUTH (KEY_ID)") == 3
    for pair in (
        "ACTIVE_KEY_ID <> GRACE_KEY_ID",
        "ACTIVE_KEY_ID <> PENDING_KEY_ID",
        "GRACE_KEY_ID <> PENDING_KEY_ID",
    ):
        assert pair in source


def test_legacy_patch_changes_only_known_status_constraint_not_columns():
    source = sql_source(SQL_FILES[4])
    assert source.count("ALTER TABLE API_KEY_AUTH") == 2
    assert "DROP CONSTRAINT CK_API_KEY_AUTH_STATUS" in source
    assert "ADD CONSTRAINT CK_API_KEY_AUTH_STATUS" in source
    assert "ENABLE VALIDATE" in source
    assert not re.search(
        r"\b(?:RENAME|MODIFY|ACTIVE_AT|EXPIRED_AT|COMMIT|INSERT|UPDATE|DELETE)\b", source
    )


def test_seed_only_inserts_missing_global_row_without_mint_or_existing_state_mutation():
    source = sql_source(SQL_FILES[5])
    assert "MERGE INTO API_KEY_ROTATION_STATE" in source
    assert "SELECT 'GLOBAL' AS SCOPE_ID FROM DUAL" in source
    assert "WHEN NOT MATCHED THEN" in source
    assert "INSERT (SCOPE_ID, VERSION)" in source
    assert "VALUES (SOURCE.SCOPE_ID, 0)" in source
    assert "WHEN MATCHED" not in source
    assert not re.search(r"\b(?:UPDATE|DELETE|KEY_HASH|API_KEY_AUTH|DBMS_RANDOM)\b", source)
    assert len(re.findall(r"\bCOMMIT\b", source)) == 1


@pytest.mark.parametrize("relative", SQL_FILES)
def test_sql_does_not_create_business_routines_or_mutate_historic_key_routines(relative):
    source = sql_source(relative)
    assert not re.search(
        r"\b(?:CREATE|ALTER|DROP)\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE|PACKAGE|TRIGGER)\b",
        source,
    )
    assert not re.search(r"\b(?:DBMS_\w+|STANDARD_HASH)\s*(?:\.|\()", source)
    assert not re.search(
        r"\b(?:BEGIN|CALL|EXECUTE)\s+(?:F_VALIDATE_API_KEY_LOGISTIK|P_PREPARE_API_KEY|P_ROTATE_API_KEYS)\b",
        source,
    )


def test_repository_executes_plain_bound_storage_sql_not_ddl_crypto_or_business_calls():
    path = ROOT / "src/api_logistik/db/api_key_repository.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    literals = [
        node.value.upper()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    source = "\n".join(literals)
    assert not re.search(
        r"\b(?:DBMS_\w+|STANDARD_HASH|F_CRUD_KARYAWAN_LOGISTIK|F_VALIDATE_API_KEY_LOGISTIK|P_PREPARE_API_KEY|P_ROTATE_API_KEYS)\b",
        source,
    )
    assert not re.search(r"\b(?:CREATE|ALTER|DROP|TRUNCATE|COMMIT|ROLLBACK)\b", source)
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert not {"commit", "rollback", "callproc", "callfunc"}.intersection(calls)
    assert "FOR UPDATE WAIT 5" in source
    assert "RETURNING KEY_ID INTO :IDENTIFIER" in source
