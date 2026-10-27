from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from api_logistik.db.api_key_repository import ApiKeyRepository
from api_logistik.errors import AuthenticationRejected
from api_logistik.security.api_keys import hash_api_key, key_is_valid, valid_key_format

_API_KEY = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_raw_api_key(
    request: Request,
    supplied: Annotated[str | None, Security(_API_KEY)],
) -> str:
    if (
        len(request.headers.getlist("x-api-key")) != 1
        or not supplied
        or not valid_key_format(supplied)
    ):
        raise AuthenticationRejected()
    return supplied


def get_connection(
    request: Request, raw: Annotated[str, Depends(get_raw_api_key)]
) -> Iterator[Any]:
    with request.app.state.pool.connection() as connection:
        yield connection


def require_api_key(
    request: Request,
    raw: Annotated[str, Depends(get_raw_api_key)],
    connection: Annotated[Any, Depends(get_connection, scope="function")],
) -> Any:
    repository = request.app.state.auth_repository_factory(connection)
    record, state, now = repository.lookup(hash_api_key(raw))
    if record is None or not key_is_valid(record, state, now):
        raise AuthenticationRejected()
    return connection


AuthenticatedConnection = Annotated[Any, Depends(require_api_key, scope="function")]
DEFAULT_AUTH_REPOSITORY = ApiKeyRepository
