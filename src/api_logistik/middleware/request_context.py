import logging
import time
import uuid
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api_logistik.schemas.responses import envelope

_LOG = logging.getLogger("api_logistik.requests")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        status = 500
        started = False
        category: str | None = None
        begin = time.monotonic()

        async def contextual_send(message: Message) -> None:
            nonlocal status, started
            if message["type"] == "http.response.start":
                status = message["status"]
                started = True
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                message = {
                    **message,
                    "headers": headers + [(b"x-request-id", request_id.encode("ascii"))],
                }
            await send(message)

        try:
            await self.app(scope, receive, contextual_send)
        except Exception:
            category = "unhandled_exception"
            if not started:
                response = JSONResponse(
                    envelope(False, "INTERNAL_ERROR", "Terjadi kesalahan internal"),
                    status_code=500,
                )
                await response(scope, receive, contextual_send)
            else:
                raise RuntimeError("Response transmission failed") from None
        finally:
            route: Any = scope.get("route")
            path = getattr(route, "path", "<unmatched>")
            _LOG.info(
                "http_request",
                extra={
                    "request_id": request_id,
                    "method": scope["method"]
                    if scope["method"]
                    in {
                        "GET",
                        "POST",
                        "PUT",
                        "DELETE",
                        "PATCH",
                        "HEAD",
                        "OPTIONS",
                        "TRACE",
                        "CONNECT",
                    }
                    else "OTHER",
                    "route": path,
                    "status": status,
                    "duration_ms": round((time.monotonic() - begin) * 1000, 3),
                    "error_category": category
                    or scope["state"].get("error_category")
                    or ("http_error" if status >= 400 else None),
                },
            )
