import json
import logging
from dataclasses import replace
from datetime import timedelta

import oracledb
import pytest

from api_logistik.errors import DatabaseContractError, DatabaseUnavailable
from api_logistik.logging_config import SafeJsonFormatter
from api_logistik.schemas.responses import OracleResponse
from api_logistik.security.api_keys import hash_api_key

ROUTES = [
    ("POST", "/api/v1/karyawan"),
    ("GET", "/api/v1/karyawan/00001"),
    ("PUT", "/api/v1/karyawan/00001"),
    ("DELETE", "/api/v1/karyawan/00001"),
]


def test_health_is_public_and_never_acquires_database(harness):
    harness.pool_error = AssertionError("Health must not acquire a connection")
    response = harness.client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert harness.events == ["http_start"]


@pytest.mark.parametrize("method,path", ROUTES)
@pytest.mark.parametrize("header_kind", ["missing", "bad", "duplicate"])
def test_auth_rejects_headers_before_any_business_callback(harness, method, path, header_kind):
    headers = {
        "bad": [("X-API-Key", "bad")],
        "duplicate": [("X-API-Key", harness.key), ("x-api-key", harness.key)],
    }
    response = harness.client.request(method, path, headers=headers.get(header_kind, []))
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_001"
    assert harness.business_calls == []
    assert "acquire" not in harness.events


@pytest.mark.parametrize(
    "status",
    [
        "ACTIVE",
        "GRACE",
        "PENDING",
        "EXPIRED",
        "REVOKED",
        "UNKNOWN",
        "MISSING",
        "AT_EXPIRY",
        "FUTURE",
    ],
)
def test_http_auth_uses_lifecycle_and_time_boundaries(harness, status):
    if status == "GRACE":
        cutover = harness.now
        harness.record = replace(
            harness.record, status="GRACE", expires_at=cutover + timedelta(hours=24)
        )
        harness.state = replace(
            harness.state,
            active_key_id=2,
            grace_key_id=1,
            next_rotation_at=cutover + timedelta(days=7),
        )
    elif status == "MISSING":
        harness.record = None
    elif status == "AT_EXPIRY":
        harness.now = harness.record.expires_at
    elif status == "FUTURE":
        harness.now = harness.record.activates_at - timedelta(microseconds=1)
    else:
        harness.record = replace(harness.record, status=status)
    response = harness.client.get("/api/v1/karyawan/1", headers={"X-API-Key": harness.key})
    assert response.status_code == (200 if status in {"ACTIVE", "GRACE"} else 401)
    assert bool(harness.business_calls) == (status in {"ACTIVE", "GRACE"})
    assert harness.digest == hash_api_key(harness.key)
    assert harness.digest != harness.key
    assert harness.events[-2:] == ["release", "http_start"]


@pytest.mark.parametrize("location", ["pool", "auth"])
def test_database_auth_failure_is_503_and_fail_closed(harness, location):
    setattr(harness, f"{location}_error", DatabaseUnavailable())
    response = harness.client.get("/api/v1/karyawan/1", headers={"X-API-Key": harness.key})
    assert response.status_code == 503
    assert response.json()["code"] == "DB_UNAVAILABLE"
    assert harness.business_calls == []


@pytest.mark.parametrize("method,path", ROUTES)
def test_crud_status_fields_and_transaction_finish_before_http_start(harness, body, method, path):
    payload = body if method == "POST" else {k: v for k, v in body.items() if k != "id_karyawan"}
    response = harness.client.request(
        method, path, json=payload, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == (201 if method == "POST" else 200)
    assert response.json()["data"]["id_karyawan"] == "1"
    mode = {"POST": "CREATE", "GET": "READ", "PUT": "UPDATE", "DELETE": "DELETE"}[method]
    expected_fields = {k: v for k, v in body.items() if k != "id_karyawan"}
    assert harness.business_calls == [
        (mode, "00001", expected_fields if method in {"POST", "PUT"} else None)
    ]
    finish = "rollback" if method == "GET" else "commit"
    assert harness.events == ["acquire", "auth", "business", finish, "release", "http_start"]


@pytest.mark.parametrize(
    "code,status", [("KRY_001", 409), ("KRY_404", 404), ("KRY_002", 422), ("UNRECOGNIZED", 500)]
)
def test_business_false_rolls_back_and_maps_status(harness, body, code, status):
    harness.result = OracleResponse(
        success=False,
        code=code,
        message="Synthetic failure",
        data=None,
    )
    response = harness.client.post(
        "/api/v1/karyawan", json=body, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == status
    assert response.json()["code"] == ("INTERNAL_ERROR" if status == 500 else code)
    assert harness.events == ["acquire", "auth", "business", "rollback", "release", "http_start"]


@pytest.mark.parametrize(
    "error,status",
    [
        (DatabaseContractError(), 500),
        (DatabaseUnavailable(), 503),
        (oracledb.DatabaseError("synthetic-driver-detail"), 500),
        (RuntimeError("synthetic-private-detail"), 500),
    ],
)
def test_parser_driver_and_unknown_failure_roll_back_safely(harness, body, error, status):
    harness.business_error = error
    response = harness.client.post(
        "/api/v1/karyawan", json=body, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == status
    assert response.json()["success"] is False
    assert str(error) not in response.text or str(error) in {
        "Terjadi kesalahan internal",
        "Layanan database tidak tersedia",
    }
    assert harness.events == ["acquire", "auth", "business", "rollback", "release", "http_start"]


def test_commit_failure_is_unknown_outcome_without_retry(harness, body):
    harness.connection.commit_error = oracledb.DatabaseError("synthetic-commit-detail")
    response = harness.client.post(
        "/api/v1/karyawan", json=body, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "COMMIT_OUTCOME_UNKNOWN"
    assert len(harness.business_calls) == 1
    assert harness.events == ["acquire", "auth", "business", "commit", "release", "http_start"]
    assert "synthetic-commit-detail" not in response.text


@pytest.mark.parametrize(
    "method,path,status",
    [
        ("GET", "/not-a-route", 404),
        ("PATCH", "/api/v1/karyawan/1", 405),
        ("GET", "/api/v1/karyawan/no-id", 422),
    ],
)
def test_request_id_on_framework_errors(harness, method, path, status):
    response = harness.client.request(
        method, path, headers={"X-API-Key": harness.key, "X-Request-ID": "untrusted-id"}
    )
    assert response.status_code == status
    assert len(response.headers["x-request-id"]) == 32
    assert response.headers["x-request-id"] != "untrusted-id"
    assert response.json()["success"] is False


def test_server_error_request_id_and_logs_exclude_sensitive_values(harness, body, caplog):
    logger = logging.getLogger()
    logger.addHandler(caplog.handler)
    harness.business_error = RuntimeError("exception-marker-private")
    body["nama"] = "body-marker-private"
    response = harness.client.post(
        "/api/v1/karyawan?password=query-marker-private",
        json=body,
        headers={"X-API-Key": harness.key, "Authorization": "header-marker-private"},
    )
    assert response.status_code == 500
    assert response.headers["x-request-id"]
    records = [r for r in caplog.records if r.name == "api_logistik.requests"]
    assert len(records) == 1
    assert records[0].route.endswith("/karyawan")
    serialized = json.dumps([r.__dict__ for r in records], default=str)
    formatted = "\n".join(SafeJsonFormatter().format(r) for r in records)
    for secret in (
        harness.key,
        body["nama"],
        "query-marker-private",
        "header-marker-private",
        "exception-marker-private",
    ):
        assert secret not in serialized
        assert secret not in formatted
        assert secret not in response.text


def test_access_log_records_route_pattern_not_raw_identifier(harness, caplog):
    logging.getLogger().addHandler(caplog.handler)
    response = harness.client.get(
        "/api/v1/karyawan/00001?private=query-private-marker", headers={"X-API-Key": harness.key}
    )
    assert response.status_code == 200
    records = [r for r in caplog.records if r.name == "api_logistik.requests"]
    assert len(records) == 1
    assert records[0].route.endswith("/karyawan/{id}")
    assert "00001" not in json.dumps(records[0].__dict__, default=str)
    assert "query-private-marker" not in json.dumps(records[0].__dict__, default=str)


def test_formatter_whitelists_events_without_rendering_messages_args_or_exceptions():
    secret = "synthetic-private-log-marker"
    error = RuntimeError(secret)
    formatter = SafeJsonFormatter()

    class Unrenderable:
        def __str__(self):
            raise AssertionError("Formatter must not stringify arbitrary messages")

    for message, expected_event in (
        (secret, "server_event"),
        ("private-message-%s", "server_event"),
        (Unrenderable(), "server_event"),
        ("http_request", "http_request"),
    ):
        record = logging.LogRecord(
            "api_logistik.requests",
            logging.ERROR,
            __file__,
            1,
            message,
            (secret,),
            (RuntimeError, error, None),
            sinfo=secret,
        )
        record.exc_text = secret
        record.password = secret
        record.headers = {"X-API-Key": secret}
        encoded = formatter.format(record)
        payload = json.loads(encoded)
        assert payload["event"] == expected_event
        assert set(payload) == {"time", "level", "event"}
        assert secret not in encoded
        assert "private-message" not in encoded


def test_unknown_http_method_is_logged_as_other_without_raw_method(harness, caplog):
    logging.getLogger().addHandler(caplog.handler)
    method = "SYNTHETIC-PRIVATE-METHOD"
    response = harness.client.request(method, "/api/v1/health/live")
    assert response.status_code == 405
    assert response.headers["x-request-id"]
    records = [record for record in caplog.records if record.name == "api_logistik.requests"]
    assert len(records) == 1
    assert records[0].method == "OTHER"
    assert records[0].error_category == "http_error"
    assert method not in json.dumps(records[0].__dict__, default=str)
    assert method not in SafeJsonFormatter().format(records[0])
    assert method not in response.text


@pytest.mark.parametrize(
    "failure,status,code,category",
    [
        ("auth", 401, "AUTH_001", "AUTH_001"),
        ("database", 503, "DB_UNAVAILABLE", "DB_UNAVAILABLE"),
        ("validation", 422, "REQUEST_422", "request_validation"),
        ("unhandled", 500, "INTERNAL_ERROR", "unhandled_exception"),
        ("not_found", 404, "HTTP_404", "http_error"),
    ],
)
def test_error_response_and_logs_keep_safe_distinct_categories(
    harness,
    body,
    caplog,
    failure,
    status,
    code,
    category,
):
    logging.getLogger().addHandler(caplog.handler)
    secret = "synthetic-private-error-marker"
    headers = {"X-API-Key": harness.key}
    path = "/api/v1/karyawan"
    if failure == "auth":
        headers = {}
    elif failure == "database":
        harness.pool_error = DatabaseUnavailable()
    elif failure == "validation":
        body["unknown"] = secret
    elif failure == "unhandled":
        harness.business_error = RuntimeError(secret)
    else:
        path = "/synthetic-unmatched-route"
    response = harness.client.post(path, json=body, headers=headers)
    assert response.status_code == status
    payload = response.json()
    assert payload["code"] == code
    assert payload["success"] is False
    assert payload["data"] is None
    assert response.headers["x-request-id"]
    assert secret not in response.text
    records = [record for record in caplog.records if record.name == "api_logistik.requests"]
    assert len(records) == 1
    assert records[0].error_category == category
    assert records[0].status == status
    formatted = json.loads(SafeJsonFormatter().format(records[0]))
    assert formatted["error_category"] == category
    assert secret not in json.dumps(records[0].__dict__, default=str)
    assert secret not in json.dumps(formatted)


def test_runtime_exception_hooks_are_installed_only_by_configuration(monkeypatch, capsys):
    import runpy
    import sys
    import threading

    import api_logistik.logging_config as module

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", root.handlers.copy())
    monkeypatch.setattr(root, "level", root.level)

    def thread_sentinel(args):
        pass

    def unraisable_sentinel(args):
        pass

    monkeypatch.setattr(threading, "excepthook", thread_sentinel)
    monkeypatch.setattr(sys, "unraisablehook", unraisable_sentinel)
    monkeypatch.setattr(logging, "raiseExceptions", True)
    main_hook = sys.excepthook
    runpy.run_path(module.__file__)
    assert threading.excepthook is thread_sentinel
    assert sys.unraisablehook is unraisable_sentinel
    module.configure_logging()
    assert threading.excepthook is module._thread_exception
    assert sys.unraisablehook is module._unraisable_exception
    assert logging.raiseExceptions is False
    assert sys.excepthook is main_hook
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "kind,event", [("thread", "background_thread_failed"), ("unraisable", "unraisable_exception")]
)
def test_runtime_exception_hooks_never_render_exception_context_or_object(
    monkeypatch,
    capsys,
    caplog,
    kind,
    event,
):
    import sys
    import threading
    from types import SimpleNamespace

    from api_logistik.logging_config import configure_logging

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", root.handlers.copy())
    monkeypatch.setattr(root, "level", root.level)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(sys, "unraisablehook", sys.unraisablehook)
    monkeypatch.setattr(logging, "raiseExceptions", logging.raiseExceptions)
    configure_logging()
    root.addHandler(caplog.handler)
    secret = "synthetic-runtime-exception-private-marker"
    rendered = []

    class Canary:
        def __repr__(self):
            rendered.append("repr")
            return secret

        def __str__(self):
            rendered.append("str")
            return secret

    class PrivateError(RuntimeError):
        def __str__(self):
            rendered.append("exception")
            return secret

    error = PrivateError(secret)
    error.__context__ = RuntimeError(secret)
    args = SimpleNamespace(
        exc_type=PrivateError,
        exc_value=error,
        exc_traceback=Canary(),
        thread=Canary(),
        object=Canary(),
        err_msg=secret,
    )
    hook = threading.excepthook if kind == "thread" else sys.unraisablehook
    hook(args)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert secret not in captured.out
    assert rendered == []
    payload = json.loads(captured.out)
    assert payload["event"] == event
    assert payload["error_category"] == event
    assert set(payload) == {"time", "level", "event", "error_category"}
    records = [record for record in caplog.records if record.name == "api_logistik.runtime"]
    assert len(records) == 1
    assert records[0].exc_info is None
    assert records[0].args == ()
    assert secret not in json.dumps(records[0].__dict__, default=str)
    if kind == "thread":
        args.exc_type = SystemExit
        hook(args)
        assert capsys.readouterr().out == ""
        assert len([r for r in caplog.records if r.name == "api_logistik.runtime"]) == 1


@pytest.mark.parametrize("kind", ["thread", "unraisable"])
def test_runtime_exception_hook_logging_failure_does_not_escape_or_print_raw(
    monkeypatch,
    capsys,
    kind,
):
    import sys
    import threading
    from types import SimpleNamespace

    from api_logistik.logging_config import configure_logging

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", root.handlers.copy())
    monkeypatch.setattr(root, "level", root.level)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(sys, "unraisablehook", sys.unraisablehook)
    monkeypatch.setattr(logging, "raiseExceptions", logging.raiseExceptions)
    configure_logging()
    secret = "synthetic-handler-private-marker"

    def fail_emit(record):
        raise RuntimeError(secret)

    monkeypatch.setattr(root.handlers[0], "emit", fail_emit)
    args = SimpleNamespace(exc_type=RuntimeError, exc_value=RuntimeError(secret))
    hook = threading.excepthook if kind == "thread" else sys.unraisablehook
    hook(args)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert secret not in captured.out


def test_uvicorn_access_is_disabled_without_disabling_structured_request_logs(
    harness,
    caplog,
    capsys,
):
    from api_logistik.logging_config import configure_logging

    configure_logging()
    access = logging.getLogger("uvicorn.access")
    assert access.handlers == []
    assert access.propagate is False
    assert access.disabled is True
    assert access.hasHandlers() is False
    server = logging.getLogger("uvicorn.error")
    assert server.propagate is True
    assert server.disabled is False
    assert server.hasHandlers() is True
    logging.getLogger().addHandler(caplog.handler)
    capsys.readouterr()
    access.error("synthetic-private-access-path?password=private")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert not any(record.name == "uvicorn.access" for record in caplog.records)
    response = harness.client.get("/api/v1/health/live")
    assert response.status_code == 200
    records = [record for record in caplog.records if record.name == "api_logistik.requests"]
    assert len(records) == 1
    assert records[0].msg == "http_request"
    assert records[0].status == 200
