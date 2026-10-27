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

_OBJECTS = ("KARYAWAN", "API_KEY_AUTH", "API_KEY_ROTATION_STATE", "F_CRUD_KARYAWAN_LOGISTIK")


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
                    DATA_PRECISION, DATA_SCALE, NULLABLE
                FROM ALL_TAB_COLUMNS WHERE OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                AND TABLE_NAME IN ('KARYAWAN', 'API_KEY_AUTH', 'API_KEY_ROTATION_STATE')
                ORDER BY TABLE_NAME, COLUMN_ID""",
            )
            columns = [
                dict(
                    zip(
                        ("table", "column", "type", "bytes", "precision", "scale", "nullable"),
                        row,
                        strict=True,
                    )
                )
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE, STATUS, VALIDATED
                FROM ALL_CONSTRAINTS WHERE OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                AND TABLE_NAME IN ('KARYAWAN', 'API_KEY_AUTH', 'API_KEY_ROTATION_STATE')
                ORDER BY TABLE_NAME, CONSTRAINT_NAME""",
            )
            constraints = [
                dict(zip(("table", "name", "type", "status", "validated"), row, strict=True))
                for row in cursor.fetchall()
            ]
            cursor.execute("SELECT PRIVILEGE FROM SESSION_PRIVS ORDER BY PRIVILEGE")
            privileges = [row[0] for row in cursor.fetchall()]
            cursor.execute(
                "SELECT VALUE FROM NLS_DATABASE_PARAMETERS WHERE PARAMETER = 'NLS_CHARACTERSET'"
            )
            charset = cursor.fetchone()[0]
            cursor.execute(
                """SELECT ARGUMENT_NAME, POSITION, DATA_TYPE, IN_OUT FROM ALL_ARGUMENTS
                WHERE OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                AND OBJECT_NAME = 'F_CRUD_KARYAWAN_LOGISTIK' ORDER BY SEQUENCE""",
            )
            arguments = [
                dict(zip(("name", "position", "type", "direction"), row, strict=True))
                for row in cursor.fetchall()
            ]
            visible = {item["name"] for item in objects if item["status"] == "VALID"}
            missing = sorted(set(_OBJECTS) - visible)
            global_rows: int | None = None
            if "API_KEY_ROTATION_STATE" in visible:
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
                "read_only": True,
                "ready_for_further_integration": not missing
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
