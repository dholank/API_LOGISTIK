from typing import Any

import oracledb
from pydantic import ValidationError

from api_logistik.errors import DatabaseContractError, DatabaseUnavailable, is_availability_error
from api_logistik.schemas.responses import OracleResponse


class KaryawanRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def call(
        self, mode: str, identifier: str, fields: dict[str, str] | None = None
    ) -> OracleResponse:
        if mode not in {"CREATE", "READ", "UPDATE", "DELETE"}:
            raise DatabaseContractError()
        payload = fields or {}
        try:
            with self.connection.cursor() as cursor:
                output = cursor.var(oracledb.DB_TYPE_CLOB)
                cursor.execute(
                    """BEGIN
                        :result := F_CRUD_KARYAWAN_LOGISTIK(
                            P_MODE => :mode, P_ID_KARYAWAN => :identifier,
                            P_NAMA => :nama, P_CABANG => :cabang,
                            P_NO_TELP => :no_telp, P_STATUS => :status
                        );
                    END;""",
                    result=output,
                    mode=mode,
                    identifier=int(identifier),
                    nama=payload.get("nama"),
                    cabang=payload.get("cabang"),
                    no_telp=payload.get("no_telp"),
                    status=payload.get("status"),
                )
                raw = output.getvalue()
                if isinstance(raw, oracledb.LOB):
                    raw = raw.read()
                if not isinstance(raw, str) or len(raw) > 65536:
                    raise DatabaseContractError()
                result = OracleResponse.model_validate_json(raw)
                if (
                    result.success
                    and result.data
                    and result.data.id_karyawan != str(int(identifier))
                ):
                    raise DatabaseContractError()
                return result
        except oracledb.Error as exc:
            if is_availability_error(exc):
                raise DatabaseUnavailable() from None
            raise DatabaseContractError() from None
        except ValidationError, ValueError, TypeError, UnicodeError:
            raise DatabaseContractError() from None
