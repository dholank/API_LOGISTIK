import json

import oracledb
import pytest

from api_logistik.db.transactions import transaction
from api_logistik.preflight import inspect_storage
from api_logistik.schemas.responses import OracleResponse

pytestmark = pytest.mark.integration


def test_oracle_connectivity_and_metadata_preflight(readonly_oracle):
    probe = readonly_oracle
    with probe.safe_errors():
        with probe.pool.connection() as connection:
            with transaction(connection, write=False):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM DUAL")
                    probe.check(cursor.fetchone() == (1,), "CONNECTIVITY_PROBE_FAILED")
        report = inspect_storage(probe.pool)
        probe.check(report["read_only"] is True, "PREFLIGHT_NOT_READ_ONLY")
        probe.check(report["missing_objects"] == [], "REQUIRED_OBJECTS_MISSING")
        probe.check(report["global_state_rows"] == 1, "GLOBAL_ROW_REQUIRED")
        probe.check(report["charset"] == "AL32UTF8", "AL32UTF8_REQUIRED")
        probe.check(report["ready_for_further_integration"] is True, "PREFLIGHT_NOT_READY")
        probe.check(
            report["live_dml_and_function_behavior_tested"] is False, "PREFLIGHT_MUST_NOT_CLAIM_DML"
        )


def test_oracle_19c_synthetic_sql_json_clob_round_trip(readonly_oracle):
    probe = readonly_oracle
    synthetic = 'Synthetic "quoted" \\ café'
    with probe.safe_errors():
        with probe.pool.connection() as connection:
            with transaction(connection, write=False):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT JSON_OBJECT(
                            'success' VALUE 'true' FORMAT JSON,
                            'code' VALUE 'SUCCESS',
                            'message' VALUE :synthetic,
                            'data' VALUE JSON_OBJECT(
                                'id_karyawan' VALUE '00001',
                                'nama' VALUE :synthetic,
                                'cabang' VALUE 'Test',
                                'no_telp' VALUE '001',
                                'status' VALUE 'AKTIF'
                                NULL ON NULL RETURNING CLOB STRICT
                            ) FORMAT JSON
                            NULL ON NULL RETURNING CLOB STRICT
                        ) FROM DUAL""",
                        synthetic=synthetic,
                    )
                    raw = cursor.fetchone()[0]
                    probe.check(isinstance(raw, oracledb.LOB), "CLOB_LOCATOR_REQUIRED")
                    encoded = raw.read()
                    decoded = json.loads(encoded)
                    result = OracleResponse.model_validate_json(encoded)
                    probe.check(decoded["success"] is True, "JSON_BOOLEAN_REQUIRED")
                    probe.check(result.data.id_karyawan == "1", "ID_NORMALIZATION_FAILED")
                    probe.check(result.data.no_telp == "001", "PHONE_ZERO_NOT_PRESERVED")
                    probe.check(
                        result.message == synthetic and result.data.nama == synthetic,
                        "SQL_JSON_ESCAPING_FAILED",
                    )
