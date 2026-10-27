"""Source checks only; they do not compile PL/SQL or execute Oracle transactions."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = "database/seed/D_DUMMY_KARYAWAN.sql"


def source() -> str:
    text = (ROOT / SEED_PATH).read_text(encoding="utf-8")
    return re.sub(r"--[^\n]*", "", text).upper()


def test_dummy_fixture_is_explicitly_registered() -> None:
    prd = (ROOT / "docs/PRD.md").read_text(encoding="utf-8")
    assert SEED_PATH in prd
    assert "16.4 Fixture dummy karyawan" in prd


def test_fixture_generates_ten_synthetic_rows_with_valid_training_lengths() -> None:
    sql = source()
    loop = re.search(r"FOR I IN (\d+)\.\.(\d+) LOOP", sql)
    base = re.search(r"V_ID := (\d+) \+ I;", sql)
    assert loop is not None and base is not None
    first, last = map(int, loop.groups())
    identifiers = [int(base[1]) + i for i in range(first, last + 1)]
    assert identifiers == list(range(90001, 90011))
    assert "V_SUFFIX := TO_CHAR(I, 'FM00');" in sql
    name = re.search(r"P_NAMA => '([^']*)' \|\| V_SUFFIX", sql)
    phone = re.search(r"P_NO_TELP => '([^']*)' \|\| V_SUFFIX", sql)
    branch = re.search(r"P_CABANG => '([^']*)'", sql)
    status = re.search(r"P_STATUS => '([^']*)'", sql)
    assert name is not None and phone is not None and branch is not None and status is not None
    assert name[1] == "DUMMY KARYAWAN " and branch[1] == "TRAINING"
    assert status[1] == "AKTIF"
    for i in range(first, last + 1):
        suffix = f"{i:02}"
        assert 0 < len((name[1] + suffix).encode("utf-8")) <= 50
        assert 0 < len(branch[1].encode("utf-8")) <= 30
        assert 0 < len(status[1].encode("utf-8")) <= 10
        telephone = phone[1] + suffix
        assert re.fullmatch(r"0[0-9]{1,19}", telephone)


def test_business_mutations_use_only_existing_create_function() -> None:
    sql = source()
    assert sql.count("F_CRUD_KARYAWAN_LOGISTIK(") == 1
    assert "P_MODE => 'CREATE'" in sql
    assert "P_ID_KARYAWAN => V_ID" in sql
    statements = re.sub(r"'(?:[^']|'')*'", "''", sql)
    assert not re.search(
        r"\b(?:INSERT|MERGE|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|EXECUTE)\b", statements
    )
    assert "CONTINUE" not in sql


def test_response_must_be_successful_and_match_fixture_id() -> None:
    sql = source()
    assert "V_RESULT := JSON_OBJECT_T.PARSE(V_RESPONSE);" in sql
    assert sql.count(".ON_ERROR(1);") == 2
    assert "V_SUCCESS := V_RESULT.GET_BOOLEAN('SUCCESS');" in sql
    assert "V_CODE := V_RESULT.GET_STRING('CODE');" in sql
    assert "V_SUCCESS IS NULL OR NOT V_SUCCESS OR V_CODE IS NULL OR V_CODE <> 'SUCCESS'" in sql
    assert "V_DATA := V_RESULT.GET_OBJECT('DATA');" in sql
    assert "IF V_DATA IS NULL THEN" in sql
    assert "V_RESULT_ID := V_DATA.GET_STRING('ID_KARYAWAN');" in sql
    assert "V_RESULT_ID IS NULL OR V_RESULT_ID <> TO_CHAR(V_ID, 'FM99990')" in sql
    assert sql.count("RAISE_APPLICATION_ERROR(") == 3


def test_any_failure_rolls_back_entire_invocation_then_propagates() -> None:
    sql = source()
    assert sql.index("SAVEPOINT SP_DUMMY_KARYAWAN;") < sql.index("FOR I IN")
    assert re.search(
        r"EXCEPTION\s+WHEN OTHERS THEN\s+ROLLBACK TO SP_DUMMY_KARYAWAN;\s+RAISE;\s+END;\s*/\s*$",
        sql,
    )
    assert not re.search(r"\bCOMMIT\b|ROLLBACK\s*;|AUTONOMOUS_TRANSACTION", sql)
    assert sql.count("SAVEPOINT ") == 1


def test_fixture_has_no_auth_side_effects_or_raw_diagnostics() -> None:
    sql = source()
    assert not re.search(
        r"\b(?:API_KEY_AUTH|API_KEY_ROTATION_STATE|KEY_HASH|SQLERRM|SQLCODE|DBMS_\w+|"
        r"F_VALIDATE_API_KEY_LOGISTIK|P_PREPARE_API_KEY|P_ROTATE_API_KEYS)\b",
        sql,
    )


def test_header_requires_manual_target_review_and_disabled_autocommit() -> None:
    text = (ROOT / SEED_PATH).read_text(encoding="utf-8").upper()
    assert "DEVELOPMENT/TRAINING ONLY" in text
    assert "VERIFY SCHEMA" in text
    assert "AUTOCOMMIT OFF" in text
    assert "REVIEW RESULTS BEFORE COMMITTING MANUALLY" in text
