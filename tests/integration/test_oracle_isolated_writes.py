from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from api_logistik.db.api_key_repository import ApiKeyRepository
from api_logistik.db.karyawan_repository import KaryawanRepository
from api_logistik.db.transactions import transaction
from api_logistik.main import create_app
from api_logistik.security.api_keys import generate_api_key

pytestmark = pytest.mark.integration


def test_bootstrap_authentication_and_crud_in_isolated_schema(isolated_oracle):
    probe = isolated_oracle
    rig = probe.rig
    with probe.safe_errors():
        state, raw = rig.bootstrap()
        probe.check(state.active_key_id in rig.key_ids, "BOOTSTRAP_POINTER_MISMATCH")
        app = create_app(rig.settings)
        application_pool = app.state.pool
        identifier = str(next(iter(rig.employee_ids)))
        route = f"/api/v1/karyawan/{identifier}"
        body = {
            "id_karyawan": identifier,
            "nama": rig.employee_names["IT"],
            "cabang": "Test",
            "no_telp": "001234",
            "status": "AKTIF",
        }
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                for headers in ({}, {"X-API-Key": generate_api_key()}):
                    response = client.get(route, headers=headers)
                    probe.check(response.status_code == 401, "INVALID_KEY_MUST_BE_401")
                headers = {"X-API-Key": raw}
                created = client.post("/api/v1/karyawan", json=body, headers=headers)
                probe.check(created.status_code == 201, "CREATE_MUST_BE_201")
                probe.check(created.json()["data"]["no_telp"] == "001234", "CREATE_PHONE_ZERO_LOST")
                duplicate = client.post("/api/v1/karyawan", json=body, headers=headers)
                probe.check(duplicate.status_code == 409, "DUPLICATE_MUST_BE_409")
                read = client.get(route, headers=headers)
                probe.check(read.status_code == 200, "READ_MUST_BE_200")
                probe.check(
                    read.json()["data"]["id_karyawan"] == identifier, "READ_IDENTIFIER_MISMATCH"
                )
                probe.check(read.json()["data"]["no_telp"] == "001234", "READ_PHONE_ZERO_LOST")
                update = {key: value for key, value in body.items() if key != "id_karyawan"}
                update["nama"] = rig.employee_names["UP"]
                update["no_telp"] = "0009"
                changed = client.put(route, json=update, headers=headers)
                probe.check(changed.status_code == 200, "UPDATE_MUST_BE_200")
                probe.check(changed.json()["data"]["no_telp"] == "0009", "UPDATE_PHONE_ZERO_LOST")
                persisted = client.get(route, headers=headers)
                probe.check(persisted.status_code == 200, "UPDATED_READ_MUST_BE_200")
                probe.check(
                    persisted.json()["data"]["nama"] == update["nama"], "UPDATE_NOT_PERSISTED"
                )
                deleted = client.delete(route, headers=headers)
                probe.check(deleted.status_code == 200, "DELETE_MUST_BE_200")
                missing = client.get(route, headers=headers)
                probe.check(missing.status_code == 404, "DELETED_ROW_MUST_BE_404")
                probe.check(missing.json()["code"] == "KRY_404", "MISSING_BUSINESS_CODE")
            probe.check(application_pool._closed is True, "APP_POOL_NOT_CLOSED_ON_SHUTDOWN")
        finally:
            application_pool.close()


def test_function_create_is_rolled_back_before_separate_session_read(isolated_oracle):
    probe = isolated_oracle
    rig = probe.rig
    identifier = str(next(iter(rig.employee_ids)))
    fields = {
        "nama": rig.employee_names["RB"],
        "cabang": "Test",
        "no_telp": "0001",
        "status": "AKTIF",
    }

    class RollbackProbe(Exception):
        pass

    with probe.safe_errors():
        other_pool = rig.new_pool()
        with rig.pool.connection() as first:
            with pytest.raises(RollbackProbe), transaction(first):
                created = KaryawanRepository(first).call("CREATE", identifier, fields)
                probe.check(created.success is True, "ROLLBACK_PROBE_CREATE_FAILED")
                raise RollbackProbe()
            # Keep the first checkout alive so the verification cannot reuse its session.
            with other_pool.connection() as second:
                with transaction(second, write=False):
                    missing = KaryawanRepository(second).call("READ", identifier)
                    probe.check(
                        missing.success is False and missing.code == "KRY_404",
                        "FUNCTION_MUTATION_ESCAPED_ROLLBACK",
                    )


def test_concurrent_prepare_has_one_canonical_pending_candidate(isolated_oracle):
    probe = isolated_oracle
    rig = probe.rig
    with probe.safe_errors():
        other_pool = rig.new_pool()
        barrier = Barrier(2)
        first, _ = rig.operator(rig.pool, barrier)
        second, _ = rig.operator(other_pool, barrier)
        # put() runs before the GLOBAL lock; both independent sessions must reach it.
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(rig.prepare, (first, second)))
        with rig.pool.connection() as connection:
            with transaction(connection, write=False):
                state = ApiKeyRepository(connection).read_state()
                probe.check(state.pending_key_id is not None, "CANONICAL_PENDING_REQUIRED")
                same_candidate = all(
                    result.pending_key_id == state.pending_key_id for result in results
                )
                probe.check(same_candidate, "CONCURRENT_PREPARE_POINTER_DIVERGENCE")
                probe.check(
                    state.version == rig.initial.version + 1, "CONCURRENT_PREPARE_DOUBLE_MUTATION"
                )
                probe.check(
                    state.pending_ready_at is None and state.active_key_id is None,
                    "PREPARE_MUST_NOT_ACTIVATE",
                )
                with connection.cursor() as cursor:
                    cursor.execute("SELECT KEY_ID, STATUS FROM API_KEY_AUTH")
                    rows = cursor.fetchall()
                    probe.check(
                        rows == [(state.pending_key_id, "PENDING")],
                        "EXACTLY_ONE_PENDING_KEY_ROW_REQUIRED",
                    )
