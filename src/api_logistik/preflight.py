import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import oracledb

from api_logistik.config import load_settings
from api_logistik.db.pool import PoolManager
from api_logistik.errors import ApplicationError, driver_error_code
from api_logistik.logging_config import configure_logging

_OBJECTS = {
    "KARYAWAN": "TABLE",
    "API_KEY_AUTH": "TABLE",
    "API_KEY_ROTATION_STATE": "TABLE",
    "F_CRUD_KARYAWAN_LOGISTIK": "FUNCTION",
}
_COLUMN_FIELDS = ("type", "precision", "scale", "nullable")
_COLUMNS: dict[str, dict[str, tuple[str, int | None, int | None, str]]] = {
    "KARYAWAN": {
        "ID_KARYAWAN": ("NUMBER", 5, 0, "N"),
        "NAMA": ("VARCHAR2", None, None, "Y"),
        "CABANG": ("VARCHAR2", None, None, "Y"),
        "NO_TELP": ("VARCHAR2", None, None, "Y"),
        "STATUS": ("VARCHAR2", None, None, "Y"),
    },
    "API_KEY_AUTH": {
        "KEY_ID": ("NUMBER", None, None, "N"),
        "KEY_HASH": ("VARCHAR2", None, None, "N"),
        "STATUS": ("VARCHAR2", None, None, "N"),
        "CREATED_AT": ("TIMESTAMP(6) WITH TIME ZONE", None, 6, "N"),
        "ACTIVATES_AT": ("TIMESTAMP(6) WITH TIME ZONE", None, 6, "Y"),
        "EXPIRES_AT": ("TIMESTAMP(6) WITH TIME ZONE", None, 6, "Y"),
    },
    "API_KEY_ROTATION_STATE": {
        "SCOPE_ID": ("VARCHAR2", None, None, "N"),
        "ACTIVE_KEY_ID": ("NUMBER", None, None, "Y"),
        "GRACE_KEY_ID": ("NUMBER", None, None, "Y"),
        "PENDING_KEY_ID": ("NUMBER", None, None, "Y"),
        "NEXT_ROTATION_AT": ("TIMESTAMP(6) WITH TIME ZONE", None, 6, "Y"),
        "PENDING_READY_AT": ("TIMESTAMP(6) WITH TIME ZONE", None, 6, "Y"),
        "VERSION": ("NUMBER", 19, 0, "N"),
        "LAST_OPERATION_ID": ("VARCHAR2", None, None, "Y"),
        "LAST_OPERATION_AT": ("TIMESTAMP(6) WITH TIME ZONE", None, 6, "Y"),
    },
}
_BYTE_LENGTHS = {
    ("KARYAWAN", "NAMA"): 50,
    ("KARYAWAN", "CABANG"): 30,
    ("KARYAWAN", "NO_TELP"): 20,
    ("KARYAWAN", "STATUS"): 10,
    ("API_KEY_AUTH", "KEY_HASH"): 64,
    ("API_KEY_AUTH", "STATUS"): 10,
    ("API_KEY_ROTATION_STATE", "SCOPE_ID"): 6,
    ("API_KEY_ROTATION_STATE", "LAST_OPERATION_ID"): 64,
}
_CONSTRAINTS = {
    "KARYAWAN": {"PK_KARYAWAN": "P"},
    "API_KEY_AUTH": {
        "PK_API_KEY_AUTH": "P",
        "UK_API_KEY_AUTH_HASH": "U",
        "CK_API_KEY_AUTH_HASH": "C",
        "CK_API_KEY_AUTH_STATUS": "C",
        "CK_API_KEY_AUTH_LIVE_DATES": "C",
        "CK_API_KEY_AUTH_WINDOW": "C",
    },
    "API_KEY_ROTATION_STATE": {
        "PK_API_KEY_ROTATION_STATE": "P",
        "CK_API_KEY_STATE_SCOPE": "C",
        "CK_API_KEY_STATE_VERSION": "C",
        "CK_API_KEY_STATE_READY": "C",
        "CK_API_KEY_STATE_NEXT": "C",
        "CK_API_KEY_STATE_OPERATION": "C",
        "CK_API_KEY_STATE_POINTERS": "C",
        "FK_API_KEY_STATE_ACTIVE": "R",
        "FK_API_KEY_STATE_GRACE": "R",
        "FK_API_KEY_STATE_PENDING": "R",
    },
}
_KEY_COLUMNS = {
    "PK_KARYAWAN": ["ID_KARYAWAN"],
    "PK_API_KEY_AUTH": ["KEY_ID"],
    "UK_API_KEY_AUTH_HASH": ["KEY_HASH"],
    "PK_API_KEY_ROTATION_STATE": ["SCOPE_ID"],
    "FK_API_KEY_STATE_ACTIVE": ["ACTIVE_KEY_ID"],
    "FK_API_KEY_STATE_GRACE": ["GRACE_KEY_ID"],
    "FK_API_KEY_STATE_PENDING": ["PENDING_KEY_ID"],
}
_ARGUMENTS = [
    (None, 0, "CLOB", "OUT", "N"),
    ("P_MODE", 1, "VARCHAR2", "IN", "N"),
    ("P_ID_KARYAWAN", 2, "NUMBER", "IN", "N"),
    ("P_NAMA", 3, "VARCHAR2", "IN", "Y"),
    ("P_CABANG", 4, "VARCHAR2", "IN", "Y"),
    ("P_NO_TELP", 5, "VARCHAR2", "IN", "Y"),
    ("P_STATUS", 6, "VARCHAR2", "IN", "Y"),
]


def _schema_issues(
    columns: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    arguments: list[dict[str, Any]],
) -> list[str]:
    issues = []
    actual_columns = {(item["table"], item["column"]): item for item in columns}
    for table, expected_columns in _COLUMNS.items():
        for name, expected in expected_columns.items():
            column = actual_columns.get((table, name))
            if column is None:
                issues.append(f"COLUMN_MISSING:{table}.{name}")
                continue
            if tuple(column[field] for field in _COLUMN_FIELDS) != expected:
                issues.append(f"COLUMN_DEFINITION:{table}.{name}")
            size = _BYTE_LENGTHS.get((table, name))
            if size is not None and (column["bytes"] != size or column["char_used"] != "B"):
                issues.append(f"COLUMN_BYTE_LENGTH:{table}.{name}")
            identity = "YES" if (table, name) == ("API_KEY_AUTH", "KEY_ID") else "NO"
            if column["identity"] != identity:
                issues.append(f"COLUMN_IDENTITY:{table}.{name}")
        for name in sorted(
            name
            for owner, name in actual_columns
            if owner == table and name not in expected_columns
        ):
            issues.append(f"COLUMN_UNEXPECTED:{table}.{name}")
    actual_constraints = {(item["table"], item["name"]): item for item in constraints}
    for table, expected_constraints in _CONSTRAINTS.items():
        for name, kind in expected_constraints.items():
            constraint = actual_constraints.get((table, name))
            if constraint is None:
                issues.append(f"CONSTRAINT_MISSING:{table}.{name}")
                continue
            if (constraint["type"], constraint["status"], constraint["validated"]) != (
                kind,
                "ENABLED",
                "VALIDATED",
            ):
                issues.append(f"CONSTRAINT_DEFINITION:{table}.{name}")
            if name in _KEY_COLUMNS and constraint["columns"] != _KEY_COLUMNS[name]:
                issues.append(f"CONSTRAINT_COLUMNS:{table}.{name}")
            if kind == "R" and constraint["reference_key"] != "PK_API_KEY_AUTH":
                issues.append(f"CONSTRAINT_REFERENCE:{table}.{name}")
    if [
        tuple(item[field] for field in ("name", "position", "type", "direction", "defaulted"))
        for item in arguments
    ] != _ARGUMENTS:
        issues.append("FUNCTION_SIGNATURE:F_CRUD_KARYAWAN_LOGISTIK")
    return issues


def inspect_storage(pool: PoolManager) -> dict[str, Any]:
    with pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT OBJECT_NAME, OBJECT_TYPE, STATUS FROM ALL_OBJECTS
                WHERE OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                AND OBJECT_NAME IN (
                    'KARYAWAN', 'API_KEY_AUTH', 'API_KEY_ROTATION_STATE', 'F_CRUD_KARYAWAN_LOGISTIK'
                )
                ORDER BY OBJECT_NAME""",
            )
            objects = [
                {"name": row[0], "type": row[1], "status": row[2]} for row in cursor.fetchall()
            ]
            cursor.execute(
                """SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, DATA_LENGTH,
                    DATA_PRECISION, DATA_SCALE, NULLABLE, CHAR_USED, IDENTITY_COLUMN
                FROM ALL_TAB_COLUMNS WHERE OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                AND TABLE_NAME IN ('KARYAWAN', 'API_KEY_AUTH', 'API_KEY_ROTATION_STATE')
                ORDER BY TABLE_NAME, COLUMN_ID""",
            )
            columns = [
                dict(
                    zip(
                        (
                            "table",
                            "column",
                            "type",
                            "bytes",
                            "precision",
                            "scale",
                            "nullable",
                            "char_used",
                            "identity",
                        ),
                        row,
                        strict=True,
                    )
                )
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE, STATUS, VALIDATED,
                    CASE WHEN R_OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                        THEN R_CONSTRAINT_NAME END
                FROM ALL_CONSTRAINTS WHERE OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                AND TABLE_NAME IN ('KARYAWAN', 'API_KEY_AUTH', 'API_KEY_ROTATION_STATE')
                ORDER BY TABLE_NAME, CONSTRAINT_NAME""",
            )
            constraints = [
                dict(
                    zip(
                        ("table", "name", "type", "status", "validated", "reference_key"),
                        row,
                        strict=True,
                    )
                )
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """SELECT TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME FROM ALL_CONS_COLUMNS
                WHERE OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                AND TABLE_NAME IN ('KARYAWAN', 'API_KEY_AUTH', 'API_KEY_ROTATION_STATE')
                ORDER BY TABLE_NAME, CONSTRAINT_NAME, POSITION"""
            )
            key_columns: dict[tuple[str, str], list[str]] = {}
            for table, name, column in cursor.fetchall():
                key_columns.setdefault((table, name), []).append(column)
            for constraint in constraints:
                constraint["columns"] = key_columns.get(
                    (constraint["table"], constraint["name"]), []
                )
            cursor.execute("SELECT PRIVILEGE FROM SESSION_PRIVS ORDER BY PRIVILEGE")
            privileges = [row[0] for row in cursor.fetchall()]
            cursor.execute(
                "SELECT VALUE FROM NLS_DATABASE_PARAMETERS WHERE PARAMETER = 'NLS_CHARACTERSET'"
            )
            charset = cursor.fetchone()[0]
            cursor.execute(
                """SELECT ARGUMENT_NAME, POSITION, DATA_TYPE, IN_OUT, DEFAULTED FROM ALL_ARGUMENTS
                WHERE OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                AND OBJECT_NAME = 'F_CRUD_KARYAWAN_LOGISTIK'
                AND PACKAGE_NAME IS NULL AND DATA_LEVEL = 0 ORDER BY SEQUENCE""",
            )
            arguments = [
                dict(zip(("name", "position", "type", "direction", "defaulted"), row, strict=True))
                for row in cursor.fetchall()
            ]
            visible = {
                item["name"]
                for item in objects
                if item["status"] == "VALID" and item["type"] == _OBJECTS[item["name"]]
            }
            missing = sorted(set(_OBJECTS) - visible)
            issues = _schema_issues(columns, constraints, arguments)
            global_rows: int | None = None
            if "API_KEY_ROTATION_STATE" in visible and any(
                item["table"] == "API_KEY_ROTATION_STATE" and item["column"] == "SCOPE_ID"
                for item in columns
            ):
                cursor.execute(
                    "SELECT COUNT(*) FROM API_KEY_ROTATION_STATE WHERE SCOPE_ID = 'GLOBAL'"
                )
                global_rows = int(cursor.fetchone()[0])
            return {
                "oracle_version": connection.version,
                "thin_mode": oracledb.is_thin_mode(),
                "charset": charset,
                "objects": objects,
                "columns": columns,
                "constraints": constraints,
                "function_arguments": arguments,
                "session_privileges": privileges,
                "missing_objects": missing,
                "global_state_rows": global_rows,
                "schema_issues": issues,
                "read_only": True,
                "ready_for_further_integration": not missing
                and not issues
                and global_rows == 1
                and charset == "AL32UTF8",
                "live_dml_and_function_behavior_tested": False,
            }


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Oracle metadata preflight; SELECT only, no key values."
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    pool: PoolManager | None = None
    try:
        pool = PoolManager(load_settings(args.env_file))
        report = inspect_storage(pool)
        encoded = json.dumps(report, indent=2, default=str)
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(encoded + "\n")
        print(encoded)
        return 0 if report["ready_for_further_integration"] else 2
    except oracledb.Error as exc:
        print(json.dumps({"ok": False, "error_code": driver_error_code(exc)}))
        return 1
    except ApplicationError as exc:
        print(json.dumps({"ok": False, "error_code": exc.code}))
        return 1
    except Exception:
        print(json.dumps({"ok": False, "error_code": "PREFLIGHT_FAILED"}))
        return 1
    finally:
        if pool:
            pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
