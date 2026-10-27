from typing import Annotated, Any

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse

from api_logistik.api.dependencies import AuthenticatedConnection
from api_logistik.db.transactions import transaction
from api_logistik.errors import BusinessFailure, DatabaseContractError
from api_logistik.schemas.karyawan import CreateKaryawan, UpdateKaryawan
from api_logistik.schemas.responses import BUSINESS_STATUS, ErrorResponse, OracleResponse

router = APIRouter(
    prefix="/karyawan",
    tags=["karyawan"],
    responses={
        status: {"model": ErrorResponse} for status in (400, 401, 404, 405, 409, 422, 500, 503)
    },
)
EmployeeId = Annotated[str, Path(pattern=r"^[0-9]{1,5}$", min_length=1, max_length=5)]


def _execute(
    request: Request,
    connection: Any,
    mode: str,
    identifier: str,
    fields: dict[str, str] | None = None,
) -> JSONResponse:
    with transaction(connection, write=mode != "READ"):
        result = request.app.state.karyawan_repository_factory(connection).call(
            mode, identifier, fields
        )
        if not result.success:
            status = BUSINESS_STATUS.get(result.code)
            if status is None:
                raise DatabaseContractError()
            raise BusinessFailure(result.code, result.message, status)
        response = JSONResponse(
            result.model_dump(mode="json"),
            status_code=201 if mode == "CREATE" else 200,
        )
    return response


@router.post("", status_code=201, response_model=OracleResponse)
def create(
    request: Request, body: CreateKaryawan, connection: AuthenticatedConnection
) -> JSONResponse:
    fields = body.model_dump(exclude={"id_karyawan"})
    return _execute(request, connection, "CREATE", body.id_karyawan, fields)


@router.get("/{id}", response_model=OracleResponse)
def read(request: Request, id: EmployeeId, connection: AuthenticatedConnection) -> JSONResponse:
    return _execute(request, connection, "READ", id)


@router.put("/{id}", response_model=OracleResponse)
def update(
    request: Request, id: EmployeeId, body: UpdateKaryawan, connection: AuthenticatedConnection
) -> JSONResponse:
    return _execute(request, connection, "UPDATE", id, body.model_dump())


@router.delete("/{id}", response_model=OracleResponse)
def delete(request: Request, id: EmployeeId, connection: AuthenticatedConnection) -> JSONResponse:
    return _execute(request, connection, "DELETE", id)
