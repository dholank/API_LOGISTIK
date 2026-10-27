from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api_logistik.schemas.karyawan import KaryawanData


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    code: str
    message: str
    data: None = None


class HealthData(BaseModel):
    status: Literal["alive"] = "alive"


class HealthResponse(BaseModel):
    success: Literal[True] = True
    code: Literal["SUCCESS"] = "SUCCESS"
    message: str
    data: HealthData


class OracleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    success: bool
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9_]+$")
    message: str = Field(min_length=1, max_length=300)
    data: KaryawanData | None

    @model_validator(mode="after")
    def consistent(self) -> OracleResponse:
        if self.success and (self.code != "SUCCESS" or self.data is None):
            raise ValueError("Invalid success response")
        if not self.success and self.data is not None:
            raise ValueError("Error response must not carry employee data")
        return self


def envelope(success: bool, code: str, message: str, data: Any = None) -> dict[str, Any]:
    return {"success": success, "code": code, "message": message, "data": data}


BUSINESS_STATUS = {
    "KRY_001": 409,
    "KRY_404": 404,
    **{f"KRY_{index:03}": 422 for index in range(2, 21)},
}
