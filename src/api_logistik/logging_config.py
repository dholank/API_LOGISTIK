import json
import logging
import sys
import threading
from datetime import UTC, datetime

_ALLOWED = {
    "request_id",
    "method",
    "route",
    "status",
    "duration_ms",
    "error_category",
    "operation_id",
    "actor",
    "action",
    "key_id",
    "version",
    "result",
    "reason",
    "pending_key_id",
    "next_rotation_at",
    "error_code",
}


_EVENTS = {
    "http_request",
    "operator_intent",
    "operator_result",
    "operator_failed",
    "rotation_blocked",
    "connection_release_failed",
    "pool_shutdown_failed",
    "uncertain_connection_drop_failed",
    "pool_initialization_failed",
    "pool_acquire_failed",
    "background_thread_failed",
    "unraisable_exception",
}


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.msg
            if isinstance(record.msg, str) and record.msg in _EVENTS
            else "server_event",
        }
        for name in _ALLOWED:
            value = record.__dict__.get(name)
            if value is not None:
                payload[name] = value
        return json.dumps(payload, ensure_ascii=True, default=str)


def _report_runtime_failure(event: str) -> None:
    try:
        logging.getLogger("api_logistik.runtime").error(event, extra={"error_category": event})
    except BaseException:
        # A failing exception hook falls back to an unsanitized interpreter traceback.
        pass


def _thread_exception(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is not SystemExit:
        _report_runtime_failure("background_thread_failed")


def _unraisable_exception(args: object) -> None:
    _report_runtime_failure("unraisable_exception")


def configure_logging() -> None:
    logging.raiseExceptions = False
    threading.excepthook = _thread_exception
    sys.unraisablehook = _unraisable_exception
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SafeJsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = name != "uvicorn.access"
        logger.disabled = name == "uvicorn.access"
