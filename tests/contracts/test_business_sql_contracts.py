"""Offline source contracts only; these do not compile or execute Oracle SQL."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = "database/schema/T_KARYAWAN.sql"
FUNCTION_PATH = "database/functions/F_CRUD_KARYAWAN_LOGISTIK.sql"


def source(path: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    return re.sub(r"--[^\n]*", "", text).upper()


def function_body() -> str:
    return source(FUNCTION_PATH).split("END MAKE_KARYAWAN_DATA;", 1)[1]


@pytest.mark.parametrize("path", [TABLE_PATH, FUNCTION_PATH])
def test_business_sources_are_fresh_only_without_extra_schema_objects(path: str) -> None:
    sql = source(path)
    assert not re.search(r"\b(?:DROP|TRUNCATE|ALTER|REPLACE)\b", sql)
    creates = re.findall(r"\bCREATE\s+(\w+)\s+(\w+)", sql)
    expected = (
        ("TABLE", "KARYAWAN") if path == TABLE_PATH else ("FUNCTION", "F_CRUD_KARYAWAN_LOGISTIK")
    )
    assert creates == [expected]
    assert "FRESH-ONLY" in (ROOT / path).read_text(encoding="utf-8").upper()


def test_training_table_has_only_registered_columns_and_primary_key() -> None:
    sql = source(TABLE_PATH)
    assert re.search(r"ID_KARYAWAN\s+NUMBER\(5\)\s+NOT NULL", sql)
    for column, length in (("NAMA", 50), ("CABANG", 30), ("NO_TELP", 20), ("STATUS", 10)):
        assert re.search(rf"\b{column}\s+VARCHAR2\({length} BYTE\)", sql)
    assert "CONSTRAINT PK_KARYAWAN PRIMARY KEY (ID_KARYAWAN)" in sql
    definitions = sql.split("(", 1)[1].rsplit(")", 1)[0].split(",")
    assert len(definitions) == 6
    assert sql.count("CONSTRAINT") == 1


def test_crud_signature_and_helpers_remain_registered_and_nested() -> None:
    sql = source(FUNCTION_PATH)
    assert re.search(
        r"CREATE FUNCTION F_CRUD_KARYAWAN_LOGISTIK\s*\(\s*"
        r"P_MODE IN VARCHAR2,\s*P_ID_KARYAWAN IN NUMBER,\s*"
        r"P_NAMA IN VARCHAR2 DEFAULT NULL,\s*P_CABANG IN VARCHAR2 DEFAULT NULL,\s*"
        r"P_NO_TELP IN VARCHAR2 DEFAULT NULL,\s*P_STATUS IN VARCHAR2 DEFAULT NULL\s*"
        r"\) RETURN CLOB\s+IS",
        sql,
    )
    assert re.findall(r"\bFUNCTION\s+(\w+)", sql) == [
        "F_CRUD_KARYAWAN_LOGISTIK",
        "MAKE_RESPONSE",
        "MAKE_KARYAWAN_DATA",
    ]
    assert sql.index("FUNCTION MAKE_RESPONSE") < sql.index("END MAKE_RESPONSE;")
    assert sql.index("FUNCTION MAKE_KARYAWAN_DATA") < sql.index("END MAKE_KARYAWAN_DATA;")
    assert sql.rstrip().endswith("END F_CRUD_KARYAWAN_LOGISTIK;\n/")


def test_transaction_control_dynamic_sql_and_sensitive_diagnostics_are_absent() -> None:
    sql = source(FUNCTION_PATH)
    assert not re.search(
        r"\b(?:COMMIT|ROLLBACK|AUTONOMOUS_TRANSACTION|SAVEPOINT|SQLERRM|SQLCODE|"
        r"DBMS_OUTPUT|DBMS_UTILITY|DBMS_SQL|DBMS_CRYPTO|DBMS_SCHEDULER|STANDARD_HASH)\b",
        sql,
    )
    assert not re.search(r"\bEXECUTE\s+IMMEDIATE\b", sql)
    assert "||" not in sql
    assert not re.search(r"SELECT\s+F_CRUD_KARYAWAN_LOGISTIK\s*\(", sql)


def test_id_validation_precedes_dml_without_precision_constrained_temporary() -> None:
    sql = source(FUNCTION_PATH)
    body = function_body()
    first_dml = body.index("INSERT INTO KARYAWAN")
    for check in (
        "P_ID_KARYAWAN IS NULL",
        "P_ID_KARYAWAN < 0",
        "P_ID_KARYAWAN > 99999",
        "P_ID_KARYAWAN <> TRUNC(P_ID_KARYAWAN)",
    ):
        assert body.index(check) < first_dml
    assert not re.search(r"NUMBER\s*\(\s*5\s*\)|%TYPE", sql)
    assert "TO_CHAR(P_ID_KARYAWAN, 'FM99990'" in sql
    assert "NLS_NUMERIC_CHARACTERS=''.,''" in sql


def test_only_create_update_require_fields_and_buffers_do_not_narrow_early() -> None:
    sql = source(FUNCTION_PATH)
    body = function_body()
    validation = body.split("IF V_MODE IN ('CREATE', 'UPDATE') THEN", 1)[1]
    validation = validation.split("CASE V_MODE", 1)[0]
    for column in ("NAMA", "CABANG", "NO_TELP", "STATUS"):
        assert f"V_{column} VARCHAR2(32767);" in sql
        assert f"V_{column} IS NULL" in validation
        assert f"NOT REGEXP_LIKE(V_{column}, '[^[:SPACE:]]')" in validation
    for column, limit in (("NAMA", 50), ("CABANG", 30), ("NO_TELP", 20), ("STATUS", 10)):
        assert f"LENGTHB(V_{column}) > {limit}" in validation
    for column in ("NAMA", "CABANG", "STATUS"):
        assert f"V_{column} := TRIM(P_{column});" in validation
    assert "V_NO_TELP := P_NO_TELP;" in validation
    assert "TRANSLATE(V_NO_TELP, 'X0123456789', 'X') IS NOT NULL" in validation
    assert not re.search(r"(?:TO_NUMBER|CAST)\s*\(\s*(?:P|V)_NO_TELP", sql)
    assert not re.search(r"V_STATUS\s+(?:NOT\s+)?IN\s*\(", sql)


@pytest.mark.parametrize("mode", ["CREATE", "READ", "UPDATE", "DELETE"])
def test_all_four_modes_are_dispatched(mode: str) -> None:
    assert f"WHEN '{mode}' THEN" in function_body()


def test_insert_uses_primary_key_conflict_and_read_uses_no_data_found() -> None:
    body = function_body()
    assert "COUNT(" not in body
    create = body.split("WHEN 'CREATE' THEN", 1)[1].split("WHEN 'READ' THEN", 1)[0]
    assert "INSERT INTO KARYAWAN (ID_KARYAWAN, NAMA, CABANG, NO_TELP, STATUS)" in create
    assert "VALUES (P_ID_KARYAWAN, V_NAMA, V_CABANG, V_NO_TELP, V_STATUS)" in create
    assert re.search(r"WHEN DUP_VAL_ON_INDEX THEN\s+RETURN MAKE_RESPONSE\('KRY_001'", create)
    read = body.split("WHEN 'READ' THEN", 1)[1].split("WHEN 'UPDATE' THEN", 1)[0]
    assert "FROM KARYAWAN" in read
    assert "WHERE ID_KARYAWAN = P_ID_KARYAWAN" in read
    assert re.search(r"WHEN NO_DATA_FOUND THEN\s+RETURN MAKE_RESPONSE\('KRY_404'", read)


@pytest.mark.parametrize("mode", ["UPDATE", "DELETE"])
def test_mutations_check_rowcount_immediately_before_other_sql(mode: str) -> None:
    branch = function_body().split(f"WHEN '{mode}' THEN", 1)[1]
    assert re.search(
        r"WHERE ID_KARYAWAN = P_ID_KARYAWAN;\s*"
        r"IF SQL%ROWCOUNT = 0 THEN\s*RETURN MAKE_RESPONSE\('KRY_404'",
        branch,
    )


def test_json_uses_oracle19_clobs_boolean_literals_and_nested_json() -> None:
    sql = source(FUNCTION_PATH)
    assert sql.count("SELECT JSON_OBJECT(") == 2
    assert sql.count("NULL ON NULL RETURNING CLOB STRICT") == 2
    assert re.search(
        r"'SUCCESS' VALUE CASE WHEN P_CODE = 'SUCCESS' THEN 'TRUE' ELSE 'FALSE' END\s+FORMAT JSON",
        sql,
    )
    assert re.search(
        r"'DATA' VALUE CASE WHEN P_CODE = 'SUCCESS' THEN P_DATA ELSE NULL END\s+FORMAT JSON",
        sql,
    )
    for key, value in (
        ("NAMA", "V_NAMA"),
        ("CABANG", "V_CABANG"),
        ("NO_TELP", "V_NO_TELP"),
        ("STATUS", "V_STATUS"),
    ):
        assert f"'{key}' VALUE {value}" in sql
    assert "'ID_KARYAWAN' VALUE TO_CHAR(" in sql
    assert "'CODE' VALUE P_CODE" in sql
    assert "'MESSAGE' VALUE P_MESSAGE" in sql


def test_delete_payload_retains_only_id_and_null_default_fields() -> None:
    sql = source(FUNCTION_PATH)
    branch = function_body().split("WHEN 'DELETE' THEN", 1)[1].split("END CASE;", 1)[0]
    for field in ("NAMA", "CABANG", "NO_TELP", "STATUS"):
        assert f"V_{field} VARCHAR2(32767);" in sql
        assert f"V_{field} :=" not in branch
        assert f"P_{field}" not in branch
    assert "DELETE FROM KARYAWAN WHERE ID_KARYAWAN = P_ID_KARYAWAN;" in branch


def test_error_codes_are_mappable_and_post_dml_failure_is_sanitized() -> None:
    sql = source(FUNCTION_PATH)
    codes = set(re.findall(r"MAKE_RESPONSE\('(KRY_\d{3})'", sql))
    assert codes == {f"KRY_{number:03}" for number in range(1, 14)} | {"KRY_404", "KRY_999"}
    body = function_body()
    assert re.search(
        r"V_MODE IS NULL OR V_MODE NOT IN \('CREATE', 'READ', 'UPDATE', 'DELETE'\)", body
    )
    assert body.index("'KRY_004'") < body.index("INSERT INTO KARYAWAN")
    assert re.search(
        r"END CASE;\s*V_DATA := MAKE_KARYAWAN_DATA;\s*"
        r"RETURN MAKE_RESPONSE\('SUCCESS', V_MESSAGE, V_DATA\);\s*"
        r"EXCEPTION\s*WHEN OTHERS THEN\s*"
        r"RETURN MAKE_RESPONSE\('KRY_999', 'OPERASI KARYAWAN GAGAL DIPROSES'\);",
        body,
    )
